import streamlit as st
import sqlite3
from datetime import datetime
import random
import re

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

DB_PATH = "angelito.db"

# =========================
# Helpers
# =========================
def clean_phone(x: str) -> str:
    return re.sub(r"\D+", "", x or "")

def clean_pin(x: str) -> str:
    return re.sub(r"\D+", "", x or "")

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def generate_derangement(items, max_tries=20000):
    items = [i for i in items if i]
    if len(items) < 2:
        raise ValueError("Necesitas al menos 2 participantes.")
    for _ in range(max_tries):
        shuffled = items[:]
        random.shuffle(shuffled)
        if all(a != b for a, b in zip(items, shuffled)):
            return dict(zip(items, shuffled))
    raise RuntimeError("No pude generar una asignación válida. Revisa la lista.")

def phone_to_name_map():
    return {phone: name for name, phone in PARTICIPANTS}

def valid_phones_set():
    return set(phone for _, phone in PARTICIPANTS)

def gen_pin_6():
    # 6 dígitos
    return f"{random.randint(0, 999999):06d}"

# =========================
# DB
# =========================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # si vienes de una tabla vieja sin 'pin', la recreamos
    cur.execute("PRAGMA table_info(participants)")
    cols = [r[1] for r in cur.fetchall()]
    if cols and ("phone" not in cols or "pin" not in cols):
        cur.execute("DROP TABLE participants")
        conn.commit()

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
    if pin is None:
        pin = gen_pin_6()

    # solo setea si no estaba
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
        SELECT phone, name, pin, registered_at
        FROM participants
        WHERE phone = ?
    """, (phone,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return False, None, None, None

    _phone, name, db_pin, registered_at = row
    if registered_at is None:
        return False, name, db_pin, registered_at

    # si pin no coincide => no autoriza
    if db_pin is None or pin != db_pin:
        return False, name, db_pin, registered_at

    return True, name, db_pin, registered_at

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
                st.warning("Este PIN se muestra aquí para que lo copies/guardes. Si lo pierdes, tendrás que pedirlo al organizador.")
            else:
                st.success(f"**{name}**, ya estabas registrado/a ✅")
                st.info("Si no recuerdas tu PIN, pídeselo al organizador (no lo volvemos a mostrar por seguridad).")

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
        ok, name, _, registered_at = validate_phone_pin(phone2, pin2)
        if registered_at is None:
            st.error("Debes registrarte primero antes de revelar tu asignación.")
        elif not ok:
            st.error("PIN incorrecto. Verifica el PIN que te salió al registrarte.")
        else:
            assigned_to_name, revealed_at = reveal_assignment(phone2)
            st.success(f"✅ **{name}**, te tocó regalarle a: **{assigned_to_name}** 🎁")
            st.caption(f"Revelado en: {revealed_at}")

st.markdown('</div>', unsafe_allow_html=True)

st.divider()
st.caption("Tip: Para reiniciar el sorteo en Streamlit Cloud, reinicia/redeploy la app (la BD se recrea desde cero).")
