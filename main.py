import os
import re
import shutil
from typing import Dict, List
import asyncio
from fastapi import WebSocket, WebSocketDisconnect, FastAPI, File, Form, Request, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import data
from rich.traceback import install

class ConnectionManager:
    def __init__(self):
        # user -> list of WebSocket connections (на случай нескольких вкладок)
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        if username not in self.active_connections:
            self.active_connections[username] = []
        self.active_connections[username].append(websocket)

    def disconnect(self, websocket: WebSocket, username: str):
        if username in self.active_connections:
            if websocket in self.active_connections[username]:
                self.active_connections[username].remove(websocket)
            if not self.active_connections[username]:
                del self.active_connections[username]

    async def send_personal_message(self, message: dict, username: str):
        """Отправить сообщение конкретному пользователю"""
        if username in self.active_connections:
            for connection in self.active_connections[username]:
                try:
                    await connection.send_json(message)
                except:
                    pass  # клиент отключился

    async def broadcast_to_pair(self, message: dict, user1: str, user2: str):
        """Отправить сообщение обоим участникам чата"""
        await self.send_personal_message(message, user1)
        await self.send_personal_message(message, user2)

manager = ConnectionManager()

install(show_locals=True)

app = FastAPI()
upload_dir = "users_images"
os.makedirs(upload_dir, exist_ok=True)

app.add_middleware(SessionMiddleware, secret_key="KioPlKioPlKioPlkiopl")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/users_images", StaticFiles(directory=upload_dir), name="users_image")

data.create_tables()
data.create_tables_messenger()

# Разрешённые символы для пароля
PASSWORD_PATTERN = re.compile(
    r'^[A-Za-zА-Яа-я0-9=,._!@#$%^&*<>()\-+/`"\'{\[}\]\\]+$'
)

def current_user(request: Request):
    return request.session.get("user")

# ====================== Аутентификация ======================

def current_user_from_ws(websocket: WebSocket):
    """Получение пользователя из cookie WebSocket соединения"""
    # В FastAPI WebSocket нет прямого доступа к session middleware
    # Используем query параметр при подключении
    return None  # Будем передавать username в URL
@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    # Принимаем соединение
    await manager.connect(websocket, username)
    try:
        while True:
            # Ждем сообщения от клиента (например, ping для поддержания соединения)
            data = await websocket.receive_text()
            # Можно обрабатывать дополнительные команды
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, username)
@app.get("/", response_class=HTMLResponse)
def read_form(request: Request):
    if current_user(request):
        return RedirectResponse(url="/success", status_code=303)
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request, error: str = None):
    if current_user(request):
        return RedirectResponse(url="/success", status_code=303)
    return templates.TemplateResponse("registr.html", {"request": request, "error": error})

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = None):
    if current_user(request):
        return RedirectResponse(url="/success", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/add_user")
def create_user(request: Request, name: str = Form(...), password: str = Form(...)):
    if current_user(request):
        return RedirectResponse(url="/success", status_code=303)

    name = name.strip()
    if not name or not password.strip():
        return RedirectResponse(url="/register?error=Имя или пароль не может быть пустым", status_code=303)

    if len(name) > 20:
        return RedirectResponse(url="/register?error=Имя не может быть длиннее 20 символов", status_code=303)

    if not PASSWORD_PATTERN.match(password):
        return RedirectResponse(
            url="/register?error=Пароль содержит недопустимые символы. Разрешены: латиница, кириллица, цифры и =,._!@#$%^&*<>()-+/*`\"'{[}]",
            status_code=303,
        )

    if data.check_users(name):
        return RedirectResponse(url="/register?error=Пользователь уже существует", status_code=303)

    data.add_user(name, password)
    request.session["user"] = name
    return RedirectResponse("/success", status_code=303)

@app.post("/logins")
def login(request: Request, name: str = Form(...), password: str = Form(...)):
    if data.check(name.strip(), password):
        request.session["user"] = name.strip()
        return RedirectResponse(url="/success", status_code=303)
    return RedirectResponse(url="/login?error=Неверное имя или пароль", status_code=303)

# ====================== Профиль ======================
@app.get("/success", response_class=HTMLResponse)
def page(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    user_folder = os.path.join(upload_dir, user.strip())
    photos = []
    if os.path.exists(user_folder):
        photos = [f"/users_images/{user}/{f}" for f in os.listdir(user_folder) if not f.startswith("avatar.")]

    avatar = data.get_user_avatar(user)
    return templates.TemplateResponse(
        "mypage.html",
        {"request": request, "user": user, "photos": photos, "avatar": avatar},
    )

# Новый маршрут — просмотр профиля другого пользователя
@app.get("/profile/{username}", response_class=HTMLResponse)
def user_profile(request: Request, username: str):
    me = current_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=303)

    if not data.check_users(username):
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user_folder = os.path.join(upload_dir, username.strip())
    photos = []
    if os.path.exists(user_folder):
        photos = [f"/users_images/{username}/{f}" for f in os.listdir(user_folder) if not f.startswith("avatar.")]

    avatar = data.get_user_avatar(username)
    return templates.TemplateResponse(
        "user_profile.html",  # можно использовать тот же mypage.html или отдельный
        {"request": request, "profile_user": username, "photos": photos, "avatar": avatar, "me": me},
    )

# ====================== Аватар и фото ======================
@app.post("/upload_avatar")
def upload_avatar(request: Request, file: UploadFile = File(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if not file.filename:
        return RedirectResponse(url="/success", status_code=303)

    types = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
    if file.content_type not in types:
        return RedirectResponse(url="/success", status_code=303)

    user_folder = os.path.join(upload_dir, user)
    os.makedirs(user_folder, exist_ok=True)

    # Удаляем старый аватар
    for old in os.listdir(user_folder):
        if old.startswith("avatar."):
            try:
                os.remove(os.path.join(user_folder, old))
            except OSError:
                pass

    ext = types[file.content_type]
    file_name = f"avatar.{ext}"
    file_path = os.path.join(user_folder, file_name)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    avatar_url = f"/users_images/{user}/{file_name}"
    data.set_user_avatar(user, avatar_url)
    return RedirectResponse(url="/success", status_code=303)

@app.post("/upload_photo")
def upload(request: Request, file: UploadFile = File(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    if not file.filename:
        return RedirectResponse(url="/success", status_code=303)

    types = ["image/jpeg", "image/png", "image/gif", "image/jpg", "image/webp"]
    if file.content_type not in types:
        return RedirectResponse(url="/success", status_code=303)

    user_folder = os.path.join(upload_dir, user)
    os.makedirs(user_folder, exist_ok=True)

    safe_file = os.path.basename(file.filename)
    file_path = os.path.join(user_folder, safe_file)

    # Удаляем старую версию с таким же именем
    if os.path.exists(file_path):
        data.delete_photo(file_path)
        try:
            os.remove(file_path)
        except OSError:
            pass

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    data.add_photo(user, file_path)
    return RedirectResponse(url="/success", status_code=303)

@app.post("/delete_photo")
def delete(request: Request, photo: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    target_file = os.path.normpath(photo.lstrip("/"))
    user_folder = os.path.normpath(os.path.join(upload_dir, user))

    if not target_file.startswith(user_folder + os.sep):
        return RedirectResponse(url="/success", status_code=303)

    # Если это был аватар — сбрасываем его
    avatar = data.get_user_avatar(user)
    if avatar and avatar == photo:
        data.set_user_avatar(user, None)

    data.delete_photo(target_file)
    if os.path.exists(target_file):
        os.remove(target_file)

    return RedirectResponse(url="/success", status_code=303)

# Установить фото как аватар
@app.post("/set_as_avatar")
def set_as_avatar(request: Request, photo: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    target_file = os.path.normpath(photo.lstrip("/"))
    user_folder = os.path.normpath(os.path.join(upload_dir, user))

    if not target_file.startswith(user_folder + os.sep):
        return RedirectResponse(url="/success", status_code=303)

    data.set_user_avatar(user, photo)
    return RedirectResponse(url="/success", status_code=303)

@app.get("/logout")
def logout(request: Request):
    request.session.pop("user", None)
    return RedirectResponse(url="/", status_code=303)

# ====================== Мессенджер ======================
@app.get("/message", response_class=HTMLResponse)
def messages_page(request: Request, recipient: str = "", reci: str = ""):
    me = current_user(request)
    if not me:
        return RedirectResponse(url="/", status_code=303)

    recipient = (recipient or reci or "").strip()
    history = []

    if recipient:
        rows = data.get_chat_history(me, recipient)
        history = [
            {
                "id": row[0],
                "sender": row[1],
                "text": row[2],
                "timestamp": row[3],
                "iso_time": row[4],          # ← Важно!
                "avatar": data.get_user_avatar(row[1]),
            }
            for row in rows
        ]

    dialogs = [
        {"name": d, "avatar": data.get_user_avatar(d)}
        for d in data.get_dialog(me)
    ]

    context = {
        "request": request,
        "user": me,
        "recipient": recipient,
        "history": history,
        "dialogs": dialogs,
        "my_avatar": data.get_user_avatar(me),
        "recipient_avatar": data.get_user_avatar(recipient) if recipient else None,
    }

    template = templates.TemplateResponse("message.html", context)
    if request.headers.get("X-Partial") == "1":
        return template
    return template

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    me = current_user_from_ws(websocket)  # нужно реализовать
    if not me or me != username:  # защита — только свой username
        await websocket.close()
        return

    await manager.connect(websocket, username)
    try:
        while True:
            # Можно принимать ping/pong или другие сообщения
            data = await websocket.receive_text()
            # Пока ничего не делаем — отправка сообщений идёт через HTTP POST
    except WebSocketDisconnect:
        manager.disconnect(websocket, username)

# Получение актуального списка диалогов (для реального времени)
@app.get("/get_dialogs")
def get_dialogs(request: Request):
    me = current_user(request)
    if not me:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    dialogs = [
        {"name": d, "avatar": data.get_user_avatar(d)}
        for d in data.get_dialog(me)
    ]
    return JSONResponse(content=dialogs)
@app.get("/get_new_messages")
def get_new_messages(request: Request, recipient: str, after_id: int = 0):
    me = current_user(request)
    if not me:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})

    recipient = recipient.strip()
    if not recipient or recipient == me:
        return JSONResponse(content=[])

    # Получаем только новые сообщения
    rows = data.get_chat_history_after(me, recipient, after_id)  # нужно добавить эту функцию

    messages = [
        {
            "id": row[0],
            "sender": row[1],
            "text": row[2],
            "timestamp": row[3],
            "avatar": data.get_user_avatar(row[1]),
        }
        for row in rows
    ]
    return JSONResponse(content=messages)
@app.post("/start_chat")
def start_chat(request: Request, contact_name: str = Form(...)):
    me = current_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=303)

    contact_name = contact_name.strip()
    if not contact_name or contact_name == me:
        return RedirectResponse(url="/message", status_code=303)

    if data.check_users(contact_name):
        data.create_chats(me, contact_name)
        return RedirectResponse(url=f"/message?recipient={contact_name}", status_code=303)

    return RedirectResponse(url="/message?error=Пользователь+не+найден", status_code=303)

@app.post("/send_message")
async def send_msg(request: Request, text: str = Form(...), recipient: str = Form(...)):
    me = current_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=303)

    recipient_clean = recipient.strip()
    text_clean = text.strip()
    if not recipient_clean or not text_clean:
        return RedirectResponse(url=f"/message?recipient={recipient_clean}", status_code=303)

    # Сохраняем сообщение
    message_id = data.send_private_message(me, recipient_clean, text_clean)  # предполагаю, что функция возвращает id
    data.create_chats(me, recipient_clean)

    # Формируем данные для фронта
    msg_data = {
        "type": "new_message",
        "id": message_id,
        "sender": me,
        "text": text_clean,
        "timestamp": "только что",  # или нормальное время
        "avatar": data.get_user_avatar(me),
        "is_own": True
    }

    # Мгновенно отправляем обоим участникам
    await manager.broadcast_to_pair(msg_data, me, recipient_clean)

    # Для обратной совместимости (если кто-то открыл через обычный GET)
    return RedirectResponse(url=f"/message?recipient={recipient_clean}", status_code=303)

@app.post("/edit_message")
def edit_message(request: Request, message_id: int = Form(...), new_text: str = Form(...), recipient: str = Form(...)):
    me = current_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=303)
    new_text = new_text.strip()
    if not new_text:
        return RedirectResponse(url=f"/message?recipient={recipient}", status_code=303)
    data.edit_message(message_id, me, new_text)
    return RedirectResponse(url=f"/message?recipient={recipient}", status_code=303)

@app.post("/delete_chat")
def delete_chat(request: Request, recipient: str = Form(...)):
    me = current_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=303)
    data.delete_dialog(me, recipient.strip())
    return RedirectResponse(url="/message", status_code=303)

@app.post("/delete_message")
def delete_message(request: Request, message_id: int = Form(...), recipient: str = Form(...)):
    me = current_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=303)
    data.delete_message(message_id, me)
    return RedirectResponse(url=f"/message?recipient={recipient}", status_code=303)

@app.get("/user/{username}", response_class=HTMLResponse)
def user_profile(request: Request, username: str):
    me = current_user(request)
    if not me:
        return RedirectResponse(url="/login", status_code=303)

    username = username.strip()
    if not data.check_users(username):
        return templates.TemplateResponse(
            "error.html", 
            {"request": request, "error": "Пользователь не найден"}, 
            status_code=404
        )

    user_folder = os.path.join(upload_dir, username)
    photos = []
    if os.path.exists(user_folder):
        # Исключаем аватар из галереи
        photos = [
            f"/users_images/{username}/{f}" 
            for f in os.listdir(user_folder) 
            if not f.startswith("avatar.")
        ]

    avatar = data.get_user_avatar(username)

    return templates.TemplateResponse(
        "user_profile.html",
        {
            "request": request,
            "profile_user": username,
            "photos": photos,
            "avatar": avatar,
            "me": me,                    # текущий пользователь (для проверки "это мой профиль?")
            "is_own_profile": me == username
        },
    )
