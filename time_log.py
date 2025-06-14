import os
from datetime import datetime, timedelta
import xlsxwriter
from mysql_database import get_inventory_logs_filtered
from io import BytesIO
from flask import Flask, request, jsonify

app = Flask(__name__)

def get_time_logs(start_date_str=None, end_date_str=None, filter_type="Semua"):
    return get_filtered_logs(start_date_str, end_date_str, filter_type)

def get_filtered_logs(start_date_str=None, end_date_str=None, filter_type="Semua"):
    try:
        # Tentukan start_date
        if start_date_str:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        else:
            start_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Tentukan end_date (inklusif sampai 23:59:59)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, microsecond=999999
            )
        else:
            end_date = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)

    except Exception:
        raise ValueError("Format tanggal harus 'YYYY-MM-DD'")

    # Ambil log dari database
    raw_logs = get_inventory_logs_filtered(start_date, end_date, filter_type)

    # Format hasil
    logs = []
    for row in raw_logs:
        logs.append({
            "name": row["name"],
            "barcode": row["barcode"],
            "qty_change": row["qty_change"],
            "timestamp": row["timestamp"].strftime('%Y-%m-%d %H:%M:%S') if isinstance(row["timestamp"], datetime) else row["timestamp"],
            "username": row["username"],
            "current_stock": row["current_stock"],
        })

    return logs


def export_logs_to_excel(logs):
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("Time Logs")

    headers = ["Staff", "Barcode", "Item Name", "Qty", "Type", "Timestamp"]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)

    # Buat format tanggal DD-MM-YYYY HH:MM:SS
    datetime_format = workbook.add_format({'num_format': 'dd-mm-yyyy hh:mm:ss'})

    for row, log in enumerate(logs, start=1):
        qty = log.get("qty_change", 0)
        log_type = "Masuk" if qty > 0 else "Keluar"

        # Parse timestamp string to datetime object
        raw_timestamp = log.get("timestamp", "")
        try:
            parsed_timestamp = datetime.strptime(raw_timestamp, "%Y-%m-%d %H:%M:%S")
        except Exception:
            parsed_timestamp = None  # fallback jika parsing gagal

        worksheet.write(row, 0, log.get("username", ""))
        worksheet.write(row, 1, log.get("barcode", ""))
        worksheet.write(row, 2, log.get("name", ""))
        worksheet.write(row, 3, qty)
        worksheet.write(row, 4, log_type)

        # Tulis timestamp dalam format yang sesuai
        if parsed_timestamp:
            formatted_ts = parsed_timestamp.strftime('%d-%m-%Y %H:%M:%S')
            worksheet.write(row, 5, formatted_ts)
        else:
            worksheet.write(row, 5, raw_timestamp)  # fallback


    worksheet.set_column(5, 5, 20)  # Kolom timestamp jadi lebih lebar
    workbook.close()
    output.seek(0)
    return output

@app.route("/api/ai/logs", methods=["GET"])
def api_ai_logs():
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    log_type = request.args.get("type", "Semua")

    try:
        logs = get_filtered_logs(start_date, end_date, log_type)
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5050)
