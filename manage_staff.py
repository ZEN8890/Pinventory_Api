import os
import pymysql
from mysql_database import connect
from werkzeug.security import generate_password_hash

# --- HASH PASSWORD SYSTEM PBKDF2 ---

def hash_password(plain_password):
    return generate_password_hash(plain_password, method='pbkdf2:sha256', salt_length=16)

# --- STAFF MANAGEMENT ---

# Ambil semua staff (termasuk role supervisor)
def get_all_staff():
    conn = connect()
    try:
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        # Ubah query di sini untuk menyertakan 'supervisor'
        cursor.execute("SELECT id, username, phone, role FROM users WHERE role IN ('staff', 'supervisor')")
        users = cursor.fetchall()
        return users
    finally:
        conn.close()

# Tambah staff baru
def add_staff(username, password, phone=None):
    conn = connect()
    try:
        cursor = conn.cursor()
        hashed_pw = hash_password(password)

        # Default role is 'staff' when adding new staff
        cursor.execute(
            "INSERT INTO users (username, password, role, phone) VALUES (%s, %s, 'staff', %s)",
            (username, hashed_pw, phone)
        )
        conn.commit()
        return True
    except pymysql.MySQLError as e:
        print("Add Staff MySQL Error:", e)
        return False
    except Exception as e:
        print("Add Staff General Error:", e)
        return False
    finally:
        conn.close()

# Update staff (password, phone, dan/atau role)
def update_staff(username, password=None, phone=None, role=None):
    conn = connect()
    try:
        fields, params = [], []

        if password:
            hashed_pw = hash_password(password)
            fields.append("password=%s")
            params.append(hashed_pw)
        
        if phone is not None:
            fields.append("phone=%s")
            params.append(phone)

        if role is not None: # Tambahkan kondisi untuk role
            fields.append("role=%s")
            params.append(role)

        if not fields:
            return False

        sql = f"UPDATE users SET {', '.join(fields)} WHERE username=%s"
        params.append(username)

        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        return cursor.rowcount > 0 # Cek apakah ada baris yang terpengaruh
    except pymysql.MySQLError as e:
        print("Update Staff Error:", e)
        return False
    finally:
        conn.close()

# Hapus staff
def delete_staff(username):
    conn = connect()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE username=%s", (username,))
        conn.commit()
        return cursor.rowcount > 0 # Cek apakah ada baris yang terhapus
    except pymysql.MySQLError as e:
        print("Delete Staff Error:", e)
        return False
    finally:
        conn.close()