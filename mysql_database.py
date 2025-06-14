import pymysql
from pymysql.cursors import DictCursor
from mysql.connector.cursor import MySQLCursorDict
from datetime import datetime,timedelta
def connect():
    try:
        conn = pymysql.connect(
            host="localhost",
            user="root",        # Ganti sesuai konfigurasi
            password="",        # Isi password MySQL kamu jika ada
            database="inventory_db",
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except pymysql.MySQLError as e:
        print(f"[ERROR] Gagal koneksi ke database: {e}")
        return None

def add_product(name, barcode, quantity, username):
    conn = connect()
    cursor = conn.cursor()
    name_to_log = name  # default

    try:
        # Cari produk berdasarkan barcode
        cursor.execute("SELECT id, quantity, name FROM products WHERE barcode = %s", (barcode,))
        result = cursor.fetchone()

        print("DEBUG >> Hasil SELECT:", result)  # Debug sementara

        if result and 'quantity' in result:
            product_id = result['id']
            current_qty = result['quantity']
            existing_name = result['name']

            try:
                new_qty = int(current_qty) + int(quantity)
                cursor.execute("UPDATE products SET quantity = %s WHERE id = %s", (new_qty, product_id))
                name_to_log = existing_name
            except ValueError:
                print("Error: 'quantity' di database bukan angka:", current_qty)
                conn.rollback()
                return

        else:
            cursor.execute(
                "INSERT INTO products (name, barcode, quantity) VALUES (%s, %s, %s)",
                (name, barcode, quantity)
            )

        conn.commit()

    except Exception as e:
        print("Error saat tambah/update produk:", e)
        conn.rollback()

    finally:
        try:
            conn.close()
        except:
            pass

    log_inventory_change(name_to_log, barcode, quantity,username)


def update_quantity(barcode, qty_change):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET quantity = quantity + %s WHERE barcode = %s", (qty_change, barcode))
    conn.commit()
    conn.close()

def update_quantity_by_name_barcode(name, barcode, quantity_change):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT quantity FROM products WHERE name = %s AND barcode = %s", (name, barcode))
    result = cursor.fetchone()

    if result is None:
        print(f"[WARNING] Produk '{name}' dengan barcode '{barcode}' tidak ditemukan. Lewati.")
        conn.close()
        return

    current_qty = result['quantity']  # gunakan nama kolom, bukan index!
    new_qty = current_qty + quantity_change

    cursor.execute("UPDATE products SET quantity = %s WHERE name = %s AND barcode = %s", (new_qty, name, barcode))
    conn.commit()
    conn.close()

def adjust_product_quantity(conn, barcode, qty, action):
    cursor = conn.cursor()
    # Ambil produk
    cursor.execute("SELECT * FROM products WHERE barcode = %s", (barcode,))
    product = cursor.fetchone()
    if not product:
        return False, 'Product not found'

    new_qty = product['quantity'] + qty if action == 'in' else product['quantity'] - qty
    if new_qty < 0:
        return False, 'Quantity cannot be negative'

    # Update stok
    cursor.execute("UPDATE products SET quantity = %s WHERE barcode = %s", (new_qty, barcode))
    conn.commit()
    return True, new_qty


def check_product_exists(name, barcode):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM products WHERE name = %s AND barcode = %s", (name, barcode))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def get_product_by_barcode(barcode):
    conn = connect()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name, quantity FROM products WHERE barcode = %s", (barcode,))
        result = cursor.fetchone()

        print(f"DEBUG >> Raw result: {result}")  # Tambahkan ini

        if result:
            name = result['name']
            quantity = result['quantity']
            return {"name": name, "quantity": quantity}
        else:
            print(f"DEBUG >> Produk dengan barcode '{barcode}' tidak ditemukan")
            return None
    except Exception as e:
        print("DEBUG >> Error saat mengambil produk:", e)
        return None
    finally:
        cursor.close()
        conn.close()


def get_inventory_logs_filtered(start_date=None, end_date=None, change_type=None):
    conn = connect()
    cursor = conn.cursor()

    query = """
    SELECT name, barcode, qty_change, timestamp, username, current_stock
    FROM inventory_logs
    WHERE 1 = 1
    """
    params = []

    if start_date and end_date:
        # Hapus penambahan 1 hari
        query += " AND timestamp >= %s AND timestamp <= %s"
        params.extend([start_date, end_date])

    if change_type == "Masuk":
        query += " AND qty_change > 0"
    elif change_type == "Keluar":
        query += " AND qty_change < 0"

    query += " ORDER BY timestamp DESC"

    # DEBUG QUERY
    print("==== DEBUG get_inventory_logs_filtered ====")
    print("Query:", query)
    print("Params:", params)

    cursor.execute(query, params)
    result = cursor.fetchall()

    print("Result count:", len(result))
    for idx, row in enumerate(result):
        print(f"Row {idx+1}: timestamp={row['timestamp']}, name={row['name']}, qty_change={row['qty_change']}")

    cursor.close()
    conn.close()
    return result


def get_all_products():
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products")
    result = cursor.fetchall()  # List of dicts
    cursor.close()
    conn.close()
    return result

def inventory_change(name, barcode, quantity, conn=None, cursor=None):
    """
    Update atau insert quantity produk.
    Kalau conn dan cursor tidak diberikan, buat koneksi baru.
    """
    external_connection = conn is not None and cursor is not None

    if not external_connection:
        conn = connect()
        cursor = conn.cursor()

    try:
        # Cek apakah produk sudah ada
        cursor.execute("SELECT quantity FROM products WHERE barcode = %s", (barcode,))
        result = cursor.fetchone()

        if result is not None:
            existing_qty = result[0]
            new_qty = existing_qty + quantity
            cursor.execute("UPDATE products SET quantity = %s WHERE barcode = %s", (new_qty, barcode))
            print(f"[UPDATE] {name} (barcode: {barcode}) -> Qty: {existing_qty} + {quantity} = {new_qty}")
        else:
            cursor.execute("INSERT INTO products (name, barcode, quantity) VALUES (%s, %s, %s)", (name, barcode, quantity))
            print(f"[INSERT] {name} (barcode: {barcode}) -> Qty: {quantity}")

        if not external_connection:
            conn.commit()

    except Exception as e:
        print(f"[ERROR] Gagal update/insert: {name}, {barcode}, {quantity} | {e}")
        if not external_connection:
            conn.rollback()

    finally:
        if not external_connection:
            cursor.close()
            conn.close()



def log_inventory_change(name, barcode, qty_change, username):
    conn = connect()
    cursor = conn.cursor()

    # Ambil stok saat ini dari tabel products
    cursor.execute("SELECT quantity FROM products WHERE barcode = %s", (barcode,))
    result = cursor.fetchone()
    current_stock = result["quantity"] if result else 0

    # Simpan log beserta current_stock
    cursor.execute("""
        INSERT INTO inventory_logs (name, barcode, qty_change, username, current_stock)
        VALUES (%s, %s, %s, %s, %s)
    """, (name, barcode, qty_change, username, current_stock))

    conn.commit()
    conn.close()


def verify_user(username, password):
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE username = %s AND password = %s", (username, password))
    result = cursor.fetchone()
    cursor.close()
    conn.close()

    if result:
        # Jika result berupa dict (bukan tuple), ambil dengan key
        if isinstance(result, dict):
            return result.get('role')
        else:
            return result[0]  # jika berupa tuple
    return None



def add_staff(username, password, phone):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("INSERT INTO users (username, password, phone, role) VALUES (%s, %s, %s, 'staff')", 
                           (username, password, phone))
        conn.commit()
        return True
    except Exception as e:
        print("Gagal menambahkan staff:", e)
        return False
    finally:
        conn.close()

def get_all_staffs():
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE role = 'staff'")
            return cursor.fetchall()
    finally:
        conn.close()

def search_staffs(query):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM users 
                WHERE role = 'staff' AND 
                (username LIKE %s OR phone LIKE %s)
            """, (f"%{query}%", f"%{query}%"))
            return cursor.fetchall()
    finally:
        conn.close()

def update_staff(user_id, new_username, new_password, new_phone):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE users 
                SET username = %s, password = %s, phone = %s 
                WHERE id = %s AND role = 'staff'
            """, (new_username, new_password, new_phone, user_id))
        conn.commit()
    finally:
        conn.close()

def delete_staff(user_id):
    conn = connect()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM users WHERE id = %s AND role = 'staff'", (user_id,))
        conn.commit()
    finally:
        conn.close()

def create_product_group(group_name, description=None, product_ids=[]):
    conn = connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO product_groups (group_name, description) VALUES (%s, %s)",
            (group_name, description)
        )
        group_id = cursor.lastrowid

        if product_ids:
            # Pastikan product_ids adalah list of int
            product_ids = [int(pid) for pid in product_ids if isinstance(pid, (int, str)) and str(pid).isdigit()]

            if product_ids:
                values = [(group_id, pid) for pid in product_ids]
                cursor.executemany(
                    "INSERT INTO grouping_products (group_id, product_id) VALUES (%s, %s)",
                    values
                )
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Gagal membuat grup produk: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_all_product_groups():
    conn = connect()
    cursor = conn.cursor()
    try:
        query = """
        SELECT pg.id, pg.group_name, pg.description,
               p.id AS product_id, p.name AS product_name, p.barcode, p.quantity
        FROM product_groups pg
        LEFT JOIN grouping_products gp ON pg.id = gp.group_id
        LEFT JOIN products p ON gp.product_id = p.id
        ORDER BY pg.group_name, p.name
        """
        cursor.execute(query)
        raw_data = cursor.fetchall()

        groups = {}
        for row in raw_data:
            group_id = row['id']
            if group_id not in groups:
                groups[group_id] = {
                    'id': row['id'],
                    'group_name': row['group_name'],
                    'description': row['description'],
                    'products': []
                }
            if row['product_id'] is not None:
                groups[group_id]['products'].append({
                    'id': row['product_id'],
                    'name': row['product_name'],
                    'barcode': row['barcode'],
                    'quantity': row['quantity']
                })
        return list(groups.values())
    except Exception as e:
        print(f"[ERROR] Gagal mengambil grup produk: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_product_group(group_id, new_group_name=None, new_description=None, new_product_ids=None):
    conn = connect()
    cursor = conn.cursor()
    try:
        # Update group details
        updates = []
        params = []
        if new_group_name is not None:
            updates.append("group_name = %s")
            params.append(new_group_name)
        if new_description is not None:
            updates.append("description = %s")
            params.append(new_description)

        if updates:
            query = f"UPDATE product_groups SET {', '.join(updates)} WHERE id = %s"
            params.append(group_id)
            cursor.execute(query, tuple(params))

        # Update associated products in grouping_products table
        if new_product_ids is not None:
            cursor.execute("DELETE FROM grouping_products WHERE group_id = %s", (group_id,))
            if new_product_ids:
                # Pastikan new_product_ids adalah list of int
                new_product_ids = [int(pid) for pid in new_product_ids if isinstance(pid, (int, str)) and str(pid).isdigit()]

                if new_product_ids:
                    values = [(group_id, pid) for pid in new_product_ids]
                    cursor.executemany(
                        "INSERT INTO grouping_products (group_id, product_id) VALUES (%s, %s)",
                        values
                    )
        conn.commit()
        return True
    except Exception as e:
        print(f"[ERROR] Gagal update grup produk: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def delete_product_group(group_id):
    conn = connect()
    cursor = conn.cursor()
    try:
        # ON DELETE CASCADE pada FK akan menghapus entri di grouping_products secara otomatis
        cursor.execute("DELETE FROM product_groups WHERE id = %s", (group_id,))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        print(f"[ERROR] Gagal menghapus grup produk: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()
