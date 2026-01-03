import streamlit as st
import sqlite3
from datetime import datetime
import random
import re

# =========================
# CONFIG
# =========================
DB_PATH = "angelito.db"

# ⚠️ RECOMENDADO: en Streamlit Cloud define ADMIN_PASSWORD en Secrets
# st.secrets["ADMIN_PASSWORD"]
ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "ADMIN2026")

# =========================
# PARTICIPANTES (Nombre -> Teléfono)
# =========================
PARTICIPANTS = [
    ("Lola", "8494248466"),
    ("Fabio", "8296899377"),
    ("Papo", "8098668564"),
    ("Mari", "8492663390"),
    ("Beiby", "8296612718"),
    ("Ana", "8097168082"),
    ("Andy", "8097218466"),
    ("Cris", "8293514306"),
    ("Brayan", "9084103558"),
    ("Ian", "5513439440"),
    ("Lesly", "8493783025"),
    ("Francis", "8097297790"),
    ("Camila", "8099039847"),
    ("Adrian", "8295778167"),
    ("Gabriel", "8298451552"),
    ("Enmanuel", "8295274679"),
    ("Samuel", "8299744776"),
    ("Yari", "8297683028"),
]

# =========================
# HELPERS
# =========================
def clean_phone(x: str) -> str:
    return re.sub(r"\D+", "", x or "")

def clean_pin(x: str) -> str:
    return re.sub(r"\D+", "", x or "")

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def gen_pin_6() -> str:
    return f"{random.randint(0, 999999):06d}"

def valid_phones_set():
    return set(phone for _, phone in PARTICIPANTS)

def phone_to_name_map():
    return {phone: name for name, phone in PARTICIPANTS}

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def generate_derangement(items, max_tries=20000):
    """
    Derangement: nadie se asigna a sí mismo.
    items: lista de teléfonos
    retorna dict[giver_phone] = receiver_phone
    """
    items = [i for i in items if i]
    if len(items) < 2:
        raise ValueError("Necesitas al menos 2 participantes.")

    for _ in range(max_tries):
        shuffled = items[:]
        random.shuffle(shuffled)
        if all(a != b for a, b in zip(items, shuffled)):
            return dict(zip(items, shuffled))

    raise RuntimeError("No pude generar una asignación válida. Revisa la lista.")

# =========================
# DB
# =========================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Verifica si existe tabla y columnas
    cur.execute("PRAGMA table_info(participants)")
    cols = [r[1] for r in cur.fetchall()]  # column names

    # Si viene de estructura vieja, recrea
    required = {"phone", "name", "pin", "assigned_to_phone", "assigned_to_name", "registered_at", "revealed_at"}
    if cols and not required.issubset(set(cols)):
        cur.execute("DROP TABLE participants")
        conn.commit()

    # Crea tabla si no existe
    cur.execute("""
        CREATE TABLE IF NOT EXISTS participants (
            phone TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            pin TEXT,
            assigned_to_phone TEXT NOT NULL,
            assigned_to_name TEXT NOT NULL,
            registered_at TEXT,
            revealed_at TEXT
        )
    """)
    conn.commit()

    # Si está vacía, sembrar
    cur.execute("SELECT COUNT(*) FROM participants")
    count = cur.fetchone()[0]

    if count == 0:
        phones = [phone for _, phone in PARTICIPANTS]
        assignment = generate_derangement(phones)
        p2n = phone_to_name_map()

        rows = []
        for giver_phone, receiver_phone in assignment.items():
            rows.append(
                (giver_phone, p2n[giver_phone], None, receiver_phone, p2n[receiver_phone], None, None)
            )

        cur.executemany("""
            INSERT INTO participants (phone, name, pin, assigned_to_phone, assigned_to_name, registered_at, revealed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

    conn.close()

def fetch_by_phone(phone: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT phone, name, pin, assigned_to_phone, assigned_to_name, registered_at, revealed_at
        FROM participants
        WHERE phone = ?
    """, (phone,))
    row = cur.fetchone()
    conn.close()
    return row

def register_phone(phone: str):
    """
    Registra si no estaba registrado:
    - set registered_at si es NULL
    - genera pin si es NULL
    Devuelve (name, pin, was_new)
    """
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT name, pin, registered_at
        FROM participants
        WHERE phone = ?
    """, (phone,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None, None, False

    name, pin, registered_at = row
    was_new = registered_at is None

    # Si no tiene pin, se crea
    if pin is None:
        pin = gen_pin_6()

    cur.execute("""
        UPDATE participants
        SET
            registered_at = COALESCE(registered_at, ?),
            pin = COALESCE(pin, ?)
        WHERE phone = ?
    """, (now_iso(), pin, phone))

    conn.commit()
    conn.close()
    return name, pin, was_new

def validate_phone_pin(phone: str, pin: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT name, pin, registered_at
        FROM participants
        WHERE phone = ?
    """, (phone,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return False, None, None

    name, db_pin, registered_at = row

    # Debe estar registrado
    if registered_at is None:
        return False, name, "NOT_REGISTERED"

    # Pin debe coincidir
    if db_pin is None or pin != db_pin:
        return False, name, "BAD_PIN"

    return True, name, "OK"

def reveal_assignment(phone: str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT assigned_to_name, revealed_at
        FROM participants
        WHERE phone = ?
    """, (phone,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None, None

    assigned_to_name, revealed_at = row

    if revealed_at is None:
        ts = now_iso()
        cur.execute("""
            UPDATE participants
            SET revealed_at = ?
            WHERE phone = ? AND revealed_at IS NULL
        """, (ts, phone))
        conn.commit()
        revealed_at = ts

    conn.close()
    return assigned_to_name, revealed_at

def stats():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM participants")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM participants WHERE registered_at IS NOT NULL")
    registered = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM participants WHERE revealed_at IS NOT NULL")
    revealed = cur.fetchone()[0]
    conn.close()
    return total, registered, revealed

# =========================
# ADMIN FUNCTIONS
# =========================
def get_pin_by_phone(phone: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT name, pin, registered_at FROM participants WHERE phone = ?", (phone,))
    row = cur.fetchone()
    conn.close()
    return row

def reset_pin(phone: str):
    new_pin = gen_pin_6()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE participants SET pin = ? WHERE phone = ?", (new_pin, phone))
    conn.commit()
    conn.close()
    return new_pin

def admin_overview_rows():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            name,
            phone,
            registered_at,
            revealed_at,
            assigned_to_name
        FROM participants
        ORDER BY name
    """)
    rows = cur.fetchall()
    conn.close()
    return rows

# =========================
# UI
# =========================
st.set_page_config(page_title="Angelito 🎁", page_icon="🎁", layout="centered")

st.markdown("""
<style>
.stApp{
  background: linear-gradient(180deg, #0b1220 0%, #0e1a2f 60%, #0b1220 100%);
}
.block-container{ max-width: 900px; padding-top: 2rem; }
h1,h2,h3{ color: #ffffff !important; letter-spacing: .3px; }
p, label, .stMarkdown, .stTextInput label{
  color: rgba(255,255,255,0.86) !important;
  font-size: 1.02rem;
}
.card{
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 18px;
  padding: 18px 18px;
  box-shadow: 0 10px 26px rgba(0,0,0,0.22);
}
input{
  border-radius: 14px !important;
  border: 1px solid rgba(255,255,255,0.20) !important;
  background: rgba(255,255,255,0.06) !important;
  color: #ffffff !important;
  padding: 0.85rem 0.9rem !important;
}
div.stButton > button{
  width: 100%;
  padding: 0.95rem 1.2rem !important;
  border-radius: 18px !important;
  border: 1px solid rgba(255,255,255,0.14) !important;
  background: linear-gradient(135deg, #4f46e5 0%, #2563eb 45%, #06b6d4 100%) !important;
  color: white !important;
  font-size: 1.12rem !important;
  font-weight: 800 !important;
  box-shadow: 0 12px 30px rgba(0,0,0,0.28);
}
div.stButton > button:hover{ filter: brightness(1.07); transform: translateY(-1px); }
div.stButton > button:active{ transform: translateY(1px); filter: brightness(0.98); }
[data-testid="stMetricValue"]{ color: #ffffff !important; font-weight: 800 !important; }
[data-testid="stMetricLabel"]{ color: rgba(255,255,255,0.75) !important; }
hr{ border-color: rgba(255,255,255,0.14) !important; }
</style>
""", unsafe_allow_html=True)

# init
init_db()

st.title("Angelito Los Lola 🎁")
st.write("Regístrate con tu **teléfono**. Al registrarte se te dará un **PIN**. Para revelar necesitas **teléfono + PIN**.")

total, registered, revealed = stats()
c1, c2, c3 = st.columns(3)
c1.metric("Participantes", total)
c2.metric("Registrados", registered)
c3.metric("Ya revelaron", revealed)

st.divider()

# ===== Registro =====
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("Registro (Teléfono)")

with st.form("registro"):
    phone_input = st.text_input("Tu teléfono (sin guiones):", placeholder="Ej: 8091234567")
    submit = st.form_submit_button("✅ Registrarme")

if submit:
    phone = clean_phone(phone_input)
    if phone not in valid_phones_set():
        st.error("Ese teléfono no está en la lista de participantes.")
    else:
        name, pin, was_new = register_phone(phone)
        if name is None:
            st.error("No pude encontrarte en la base (no debería pasar).")
        else:
            if was_new:
                st.success(f"Listo, **{name}**. Quedaste registrado/a ✅")
                st.info(f"🔐 Tu PIN es: **{pin}**  (Guárdalo. Lo necesitarás para revelar.)")
                st.warning("Este PIN se muestra aquí SOLO una vez para que lo copies. Si lo pierdes, pídeselo al organizador.")
            else:
                st.success(f"**{name}**, ya estabas registrado/a ✅")
                st.info("Si no recuerdas tu PIN, pídeselo al organizador (no se vuelve a mostrar por seguridad).")

st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# ===== Revelar =====
st.markdown('<div class="card">', unsafe_allow_html=True)
st.subheader("Revelar asignación (Teléfono + PIN)")

phone_input2 = st.text_input("Teléfono:", placeholder="Ej: 8091234567")
pin_input = st.text_input("PIN (6 dígitos):", placeholder="Ej: 123456", type="password")

phone2 = clean_phone(phone_input2)
pin2 = clean_pin(pin_input)

colA, colB = st.columns([1, 1])
with colA:
    reveal_btn = st.button("🎲 Revelar a quién me tocó", use_container_width=True)
with colB:
    refresh_btn = st.button("🔄 Actualizar", use_container_width=True)

if refresh_btn:
    st.rerun()

if reveal_btn:
    if phone2 not in valid_phones_set():
        st.error("Ese teléfono no está en la lista.")
    else:
        ok, name, status = validate_phone_pin(phone2, pin2)

        if status == "NOT_REGISTERED":
            st.error("Debes registrarte primero antes de revelar tu asignación.")
        elif status == "BAD_PIN":
            st.error("PIN incorrecto. Verifica el PIN que te salió al registrarte.")
        elif not ok:
            st.error("No pude validar. Intenta de nuevo.")
        else:
            assigned_to_name, revealed_at = reveal_assignment(phone2)
            st.success(f"✅ **{name}**, te tocó regalarle a: **{assigned_to_name}** 🎁")
            st.caption(f"Revelado en: {revealed_at}")

st.markdown('</div>', unsafe_allow_html=True)

st.divider()

# ===== Modo organizador =====
with st.expander("🔐 Modo organizador (solo para el organizador)"):
    admin_pass = st.text_input("Clave del organizador", type="password")
    is_admin = (admin_pass == ADMIN_PASSWORD)

    st.markdown("### Acciones")
    phone_admin = clean_phone(st.text_input("Teléfono del participante (para PIN)"))

    col1, col2 = st.columns(2)

    if col1.button("👁️ Ver PIN"):
        if not is_admin:
            st.error("Clave incorrecta.")
        elif not phone_admin:
            st.error("Escribe un teléfono.")
        else:
            row = get_pin_by_phone(phone_admin)
            if not row:
                st.error("Teléfono no encontrado.")
            else:
                name, pin, registered_at = row
                if registered_at is None:
                    st.warning(f"**{name}** aún no se ha registrado.")
                st.success(f"PIN de **{name}**: **{pin}**")

    if col2.button("♻️ Generar PIN nuevo"):
        if not is_admin:
            st.error("Clave incorrecta.")
        elif not phone_admin:
            st.error("Escribe un teléfono.")
        else:
            row = get_pin_by_phone(phone_admin)
            if not row:
                st.error("Teléfono no encontrado.")
            else:
                name, _, _ = row
                new_pin = reset_pin(phone_admin)
                st.success(f"Nuevo PIN para **{name}**: **{new_pin}**")
                st.warning("Comparte este PIN solo con esa persona.")

    st.markdown("---")
    st.markdown("### Estado del sorteo")

    if is_admin:
        rows = admin_overview_rows()
        # tabla simple sin pandas
        st.write("**Registrados / Revelados / Asignación (solo organizador):**")
        st.dataframe(
            [{
                "Nombre": r[0],
                "Teléfono": r[1],
                "Registrado": "Sí" if r[2] else "No",
                "Reveló": "Sí" if r[3] else "No",
                "Le regala a": r[4],
            } for r in rows],
            use_container_width=True
        )
    else:
        st.info("Introduce la clave correcta para ver el estado completo.")

st.caption("Tip: Para reiniciar el sorteo, elimina el archivo angelito.db (en local) o borra los datos del storage en el hosting y redeploy.")
