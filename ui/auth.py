"""
Простая аутентификация для Streamlit UI.
Хранение пользователей в файле конфигурации (JSON).

Для production стоит использовать OAuth/LDAP, но для лабы этого достаточно.
"""

import json
import os
import streamlit as st
from datetime import datetime


# Путь к файлу пользователей
AUTH_FILE = os.environ.get("AUTH_FILE", "/app/users.json")

# Время жизни сессии (часы)
SESSION_TTL_HOURS = 8


def get_default_users() -> dict:
    """
    Пользователи по умолчанию.
    В реальном проекте — в БД или LDAP, не в коде.
    """
    return {
        "admin": {
            "password": "admin123",
            "role": "admin",
            "name": "Администратор",
        },
        "engineer": {
            "password": "eng123",
            "role": "engineer",
            "name": "Инженер поддержки",
        },
        "student": {
            "password": "student123",
            "role": "student",
            "name": "Студент-заочник",
        },
    }


def load_users() -> dict:
    """Загружает пользователей из файла или создаёт по умолчанию."""
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return get_default_users()


def init_auth_state():
    """Инициализация состояния аутентификации в session_state."""
    if "auth_user" not in st.session_state:
        st.session_state["auth_user"] = None
    if "auth_login_time" not in st.session_state:
        st.session_state["auth_login_time"] = None
    if "auth_role" not in st.session_state:
        st.session_state["auth_role"] = None


def is_authenticated() -> bool:
    """Проверяет, залогинен ли пользователь."""
    return st.session_state.get("auth_user") is not None


def check_session_expired() -> bool:
    """Проверяет, не истекла ли сессия."""
    login_time = st.session_state.get("auth_login_time")
    if not login_time:
        return True
    elapsed = (datetime.now() - login_time).total_seconds()
    return elapsed > SESSION_TTL_HOURS * 3600


def login(username: str, password: str) -> tuple[bool, str]:
    """
    Проверяет логин/пароль.
    Возвращает (успех, сообщение).
    """
    users = load_users()

    if username not in users:
        return False, "Пользователь не найден"

    if users[username]["password"] != password:
        return False, "Неверный пароль"

    st.session_state["auth_user"] = username
    st.session_state["auth_role"] = users[username]["role"]
    st.session_state["auth_login_time"] = datetime.now()

    return True, f"Добро пожаловать, {users[username]['name']}!"


def logout():
    """Выход из системы."""
    st.session_state["auth_user"] = None
    st.session_state["auth_role"] = None
    st.session_state["auth_login_time"] = None


def get_current_user() -> dict | None:
    """Возвращает информацию о текущем пользователе."""
    if not is_authenticated():
        return None
    users = load_users()
    username = st.session_state.get("auth_user")
    if username in users:
        return {
            "username": username,
            "role": users[username]["role"],
            "name": users[username]["name"],
        }
    return None


def require_auth():
    """
    Главное: если не залогинен — показывает экран входа и возвращает False.
    Если залогинен — возвращает True и страница продолжается.

    Использование в app.py:
        init_auth_state()
        if not require_auth():
            st.stop()
        # ... основной код страницы ...
    """
    init_auth_state()

    # Проверка истечения сессии
    if is_authenticated() and check_session_expired():
        logout()
        st.warning("Сессия истекла. Войдите снова.")

    if not is_authenticated():
        _render_login_page()
        return False

    return True


def _render_login_page():
    """Рисует экран входа."""
    st.markdown("""
    <style>
    .login-container {
        max-width: 400px;
        margin: 0 auto;
        padding: 2rem;
    }
    .login-title {
        text-align: center;
        font-size: 1.5rem;
        font-weight: bold;
        margin-bottom: 1rem;
    }
    .login-hint {
        text-align: center;
        font-size: 0.85rem;
        color: #888;
        margin-top: 1rem;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    st.markdown('<div class="login-title">🛠️ Вход в систему ITSM</div>', unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.text_input("Логин", placeholder="admin")
        password = st.text_input("Пароль", type="password", placeholder="••••••••")
        col_btn, col_info = st.columns([1, 1])
        with col_btn:
            submitted = st.form_submit_button("Войти", type="primary", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("Введите логин и пароль")
        else:
            success, msg = login(username.strip(), password)
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    st.markdown("""
    <div class="login-hint">
    <b>Тестовые учётные записи:</b><br>
    admin / admin123 — полный доступ<br>
    engineer / eng123 — инженер<br>
    student / student123 — просмотр
    </div>
    """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


def render_user_header():
    """
    Рисует шапку с именем пользователя и кнопкой выхода.
    Вызывается в начале страницы после require_auth().
    """
    user = get_current_user()
    if not user:
        return

    col_title, col_user, col_logout = st.columns([6, 2, 1])
    with col_title:
        st.title("🛠️ ITSM: RAG + Заявки + MOLSP")
        st.caption(f"Лабораторная работа 3 — {user['name']} ({user['role']})")
    with col_user:
        role_badge = {
            "admin": "👑 Admin",
            "engineer": "🔧 Engineer",
            "student": "🎓 Student",
        }.get(user["role"], user["role"])
        st.markdown(f"**{user['name']}**")
        st.markdown(f"Роль: {role_badge}")
    with col_logout:
        if st.button("🚪 Выход"):
            logout()
            st.rerun()


def has_role(*roles) -> bool:
    """Проверяет, есть ли у пользователя одна из указанных ролей."""
    current_role = st.session_state.get("auth_role")
    return current_role in roles
