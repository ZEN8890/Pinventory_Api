from flask import Flask, request, jsonify, send_file
from mysql_database import connect, add_product, get_all_products, get_product_by_barcode, adjust_product_quantity, create_product_group, get_all_product_groups, update_product_group, delete_product_group
from inventory_importer import import_inventory_from_excel
from time_log import get_time_logs,get_filtered_logs
from exporter_timelog import export_logs_to_excel
from exporter_products import export_products_to_excel
from manage_staff import get_all_staff, add_staff, update_staff, delete_staff
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import BadRequest
import os
import logging
import re
import io
import pandas as pd
from datetime import datetime,timedelta
from flask_cors import CORS


app = Flask(__name__)
CORS(app)

app.logger.setLevel(logging.INFO)

# --- HEALTH CHECK ---
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify(status='ok')

def is_password_hashed(password):
    return bool(re.match(r'^(\$2[aby]|pbkdf2:)', password))

# --- LOGIN ---
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username_input = data.get('username')
        password_input = data.get('password')

        if not username_input or not password_input:
            return jsonify({'success': False, 'message': 'Username dan password wajib diisi'}), 400

        conn = connect()
        if conn is None:
            return jsonify({'success': False, 'message': 'Gagal koneksi ke database'}), 500

        cursor = conn.cursor()
        cursor.execute("SELECT username, password, role, phone FROM users WHERE username = %s", (username_input,))
        user = cursor.fetchone()

        if not user:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'User tidak ditemukan'}), 404

        username_db = user['username'].strip()
        password_db = user['password'].strip()
        role = user['role']
        phone = user['phone']

        username_input = username_input.strip()
        password_input = password_input.strip()

        if password_db.startswith('scrypt:') or password_db.startswith('pbkdf2:'):
            password_valid = check_password_hash(password_db, password_input)
        else:
            password_valid = (password_db == password_input)
            if password_valid:
                new_password_hash = generate_password_hash(password_input)
                cursor.execute("UPDATE users SET password = %s WHERE username = %s", (new_password_hash, username_db))
                conn.commit()

        cursor.close()
        conn.close()

        if not password_valid:
            return jsonify({'success': False, 'message': 'Password salah'}), 401

        return jsonify({
            'success': True,
            'message': 'Login berhasil',
            'role': role,
            'username': username_db,
            'phone': phone
        }), 200

    except Exception as e:
        app.logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'message': 'Internal Server Error'}), 500

# --- PRODUCTS ---
@app.route('/api/products', methods=['GET'])
def api_list_products():
    prods = get_all_products()
    return jsonify(prods)

@app.route('/api/scan', methods=['POST'])
def api_scan():
    try:
        data = request.get_json()
        barcode = data.get('barcode')
        qty = int(data.get('qty', 1))
        action = data.get('action')
        username = data.get('username')

        if not barcode or not action:
            return jsonify(success=False, message='Barcode dan action wajib diisi'), 400

        conn = connect()
        cursor = conn.cursor()

        prod = get_product_by_barcode(barcode)
        if not prod:
            return jsonify(success=False, message='Barcode not found'), 404

        success, result = adjust_product_quantity(conn, barcode, qty, action)
        if not success:
            return jsonify(success=False, message=result), 400

        updated_prod = get_product_by_barcode(barcode)

        insert_log_query = """
            INSERT INTO inventory_logs (name, barcode, qty_change, action_type, timestamp, username, current_stock)
            VALUES (%s, %s, %s, %s, NOW(), %s, %s)
        """
        cursor.execute(insert_log_query, (
            prod['name'],
            barcode,
            qty if action == 'in' else -qty,
            'IN' if action == 'in' else 'OUT',
            username,
            updated_prod['quantity']
        ))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify(success=True, product=updated_prod), 200

    except BadRequest as br:
        return jsonify(success=False, message=str(br)), 400
    except Exception as e:
        app.logger.error(f"Scan error: {e}")
        return jsonify(success=False, message='Internal Server Error'), 500

@app.route('/api/products/import', methods=['POST'])
def api_import_inventory():
    if 'file' not in request.files:
        return jsonify(error='No file part'), 400
    file = request.files['file']
    tmp_dir = 'tmp'
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, file.filename)
    file.save(tmp_path)

    try:
        count = import_inventory_from_excel(tmp_path)
    except Exception as e:
        os.remove(tmp_path)
        return jsonify(error=str(e)), 500

    os.remove(tmp_path)
    return jsonify(imported=count)

@app.route('/api/products/export', methods=['GET'])
def export_products():
    products = get_all_products()
    today_str = datetime.today().strftime('%Y-%m-%d')
    filename = f'products_{today_str}.xlsx'

    df = pd.DataFrame(products)

    if 'barcode' in df.columns:
        df['barcode'] = df['barcode'].apply(lambda x: f"'{str(x)}" if pd.notnull(x) else x)

    if 'id' in df.columns:
        df = df.drop(columns=['id'])

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)

    # Cek apakah request datang dari aplikasi lokal EXE (dengan flag khusus)
    save_to_downloads = request.args.get('save', 'false').lower() == 'true'

    if save_to_downloads:
        # Simpan langsung ke folder Downloads di Windows
        downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
        save_path = os.path.join(downloads_path, filename)

        with open(save_path, 'wb') as f:
            f.write(output.read())

        return jsonify(success=True, message=f"File berhasil disimpan ke {save_path}")

    # Jika tidak, kirim ke klien (untuk Flutter / browser)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# --- TIME LOG ---
@app.route('/api/timelog', methods=['GET'])
def api_timelog():
    start = request.args.get('start')
    end = request.args.get('end')
    change_type = request.args.get('type', "Semua")

    logs = get_time_logs(start, end, change_type)

    return jsonify(logs)

@app.route('/api/timelog/delete', methods=['POST'])
def api_timelog_bulk_delete():
    try:
        data = request.get_json()
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        log_type = data.get('type', 'Semua')

        if not start_date or not end_date:
            return jsonify(success=False, message="Start date dan end date wajib diisi"), 400

        # Pakai format eksklusif: >= start_date AND < end_date
        start_datetime = f"{start_date} 00:00:00"
        end_datetime = f"{end_date} 00:00:00"

        conn = connect()
        cursor = conn.cursor()

        if log_type == "Masuk":
            delete_query = """
                DELETE FROM inventory_logs
                WHERE timestamp >= %s AND timestamp < %s
                AND qty_change > 0
            """
        elif log_type == "Keluar":
            delete_query = """
                DELETE FROM inventory_logs
                WHERE timestamp >= %s AND timestamp < %s
                AND qty_change < 0
            """
        else:  # Semua
            delete_query = """
                DELETE FROM inventory_logs
                WHERE timestamp >= %s AND timestamp < %s
            """

        cursor.execute(delete_query, (start_datetime, end_datetime))
        conn.commit()
        rows_deleted = cursor.rowcount

        cursor.close()
        conn.close()

        return jsonify(success=True, message=f"{rows_deleted} log berhasil dihapus."), 200

    except Exception as e:
        app.logger.error(f"Bulk delete timelog error: {e}")
        return jsonify(success=False, message="Internal Server Error"), 500


@app.route('/api/timelog/<int:log_id>', methods=['DELETE'])
def api_timelog_delete(log_id):
    try:
        conn = connect()
        cursor = conn.cursor()

        delete_query = "DELETE FROM inventory_logs WHERE id = %s"
        cursor.execute(delete_query, (log_id,))
        conn.commit()

        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify(success=False, message="Log tidak ditemukan"), 404

        cursor.close()
        conn.close()
        return jsonify(success=True, message="Log berhasil dihapus"), 200

    except Exception as e:
        app.logger.error(f"Delete timelog error: {e}")
        return jsonify(success=False, message="Internal Server Error"), 500

@app.route('/api/timelog/export', methods=['GET'])
def api_timelog_export():
    start = request.args.get('start')
    end = request.args.get('end')
    change_type = request.args.get('type', "Semua")

    # Validate date inputs
    try:
        if start:
            datetime.strptime(start, '%Y-%m-%d')
        if end:
            datetime.strptime(end, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400

    logs = get_time_logs(start, end, change_type)
    excel_file = export_logs_to_excel(logs)

    today_str = datetime.today().strftime('%d-%m-%Y')  # Changed to dd-mm-yyyy
    filename = f'timelog_{today_str}.xlsx'

    response = send_file(
        excel_file,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    
    # Add headers to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

# --- MANAGE STAFF ---
@app.route('/api/staff', methods=['GET', 'POST'])
def api_staff():
    try:
        if request.method == 'GET':
            staff_data = get_all_staff()
            # Pastikan 'role' juga dikirim ke Flutter
            staff_list = [{'id': s['id'], 'username': s['username'], 'phone': s['phone'], 'role': s['role']} for s in staff_data]
            return jsonify(success=True, staff=staff_list)
        
        elif request.method == 'POST':
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
            phone = data.get('phone')

            if not username or not password:
                return jsonify(success=False, message="Username dan password wajib diisi"), 400

            success = add_staff(username, password, phone)
            if success:
                return jsonify(success=True, message="Staff berhasil dibuat")
            else:
                return jsonify(success=False, message="Gagal membuat staff (kemungkinan username sudah ada)"), 500

    except Exception as e:
        app.logger.error(f"Staff error: {e}")
        return jsonify(success=False, message=str(e)), 500

@app.route('/api/staff/<string:username>', methods=['PUT', 'DELETE'])
def api_staff_modify(username):
    try:
        if request.method == 'PUT':
            data = request.get_json()
            password = data.get('password')
            phone = data.get('phone')
            role = data.get('role') # Ambil role dari request

            if not password and phone is None and role is None: # Sertakan role dalam validasi
                return jsonify(success=False, message="Minimal password, phone, atau role harus diisi"), 400

            success = update_staff(username, password, phone, role) # Kirim role ke fungsi update_staff
            if success:
                return jsonify(success=True, message="Staff berhasil diupdate")
            else:
                return jsonify(success=False, message="Gagal update staff"), 400

        elif request.method == 'DELETE':
            success = delete_staff(username)
            if success:
                return jsonify(success=True, message="Staff berhasil dihapus")
            else:
                return jsonify(success=False, message="Gagal hapus staff"), 400

    except Exception as e:
        app.logger.error(f"Staff modify error: {e}")
        return jsonify(success=False, message=str(e)), 500

@app.route("/api/ai/logs", methods=["GET"])
def api_ai_logs():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    log_type = request.args.get("type", "Semua")  # Masuk, Keluar, atau Semua

    try:
        logs = get_filtered_logs(start_date, end_date, log_type)
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# --- PRODUCT GROUPS ---
@app.route('/api/groups', methods=['POST'])
def api_create_group():
    try:
        data = request.get_json()
        group_name = data.get('group_name')
        description = data.get('description')
        product_ids = data.get('product_ids', [])

        if not group_name:
            return jsonify(success=False, message="Nama grup wajib diisi"), 400

        success = create_product_group(group_name, description, product_ids)
        if success:
            return jsonify(success=True, message="Grup produk berhasil dibuat"), 201
        else:
            return jsonify(success=False, message="Gagal membuat grup produk"), 500
    except Exception as e:
        app.logger.error(f"Create group error: {e}")
        return jsonify(success=False, message=str(e)), 500

@app.route('/api/groups', methods=['GET'])
def api_get_all_groups():
    try:
        groups = get_all_product_groups()
        return jsonify(groups), 200
    except Exception as e:
        app.logger.error(f"Get all groups error: {e}")
        return jsonify(success=False, message=str(e)), 500

@app.route('/api/groups/<int:group_id>', methods=['PUT'])
def api_update_group(group_id):
    try:
        data = request.get_json()
        new_group_name = data.get('group_name')
        new_description = data.get('description')
        new_product_ids = data.get('product_ids') # Bisa null jika tidak ingin update products

        success = update_product_group(group_id, new_group_name, new_description, new_product_ids)
        if success:
            return jsonify(success=True, message="Grup produk berhasil diupdate"), 200
        else:
            return jsonify(success=False, message="Gagal update grup produk atau grup tidak ditemukan"), 404
    except Exception as e:
        app.logger.error(f"Update group error: {e}")
        return jsonify(success=False, message=str(e)), 500

@app.route('/api/groups/<int:group_id>', methods=['DELETE'])
def api_delete_group(group_id):
    try:
        success = delete_product_group(group_id)
        if success:
            return jsonify(success=True, message="Grup produk berhasil dihapus"), 200
        else:
            return jsonify(success=False, message="Gagal menghapus grup produk atau grup tidak ditemukan"), 404
    except Exception as e:
        app.logger.error(f"Delete group error: {e}")
        return jsonify(success=False, message=str(e)), 500

if __name__ == '__main__':
    routes = []
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'OPTIONS', 'HEAD'}))
        routes.append(f"{methods} {rule.rule}")
    app.logger.info("Available routes:\n" + "\n".join(routes))

    app.run(host='0.0.0.0', port=5000, debug=True)
