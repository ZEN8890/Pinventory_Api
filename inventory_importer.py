import pandas as pd
import os
import time
from mysql_database import connect, inventory_change

def import_inventory_from_excel(filepath):
    """
    Membaca file Excel pada `filepath`,
    kosongkan tabel products,
    masukkan data nama, barcode, quantity,
    dan buat log inventory untuk tiap baris.
    Kembalikan jumlah baris yang diimport.
    """
    df = pd.read_excel(filepath)

    # Pastikan kolom penting ada
    required_columns = {'name', 'barcode', 'quantity'}
    if not required_columns.issubset(df.columns):
        raise ValueError(f"Excel harus berisi kolom: {required_columns}")

    conn = None
    cursor = None
    imported_rows = 0
    total_rows = len(df)

    try:
        conn = connect()
        cursor = conn.cursor()

        # Hapus semua isi tabel products
        cursor.execute("DELETE FROM products")

        for index, row in df.iterrows():
            name = str(row['name']).strip()
            barcode = str(row['barcode']).strip().lstrip("'")  # buang tanda kutip di awal jika ada
            quantity = int(row['quantity'])

            if name and barcode:
                try:
                    cursor.execute(
                        "INSERT INTO products (name, barcode, quantity) VALUES (%s, %s, %s)",
                        (name, barcode, quantity)
                    )
                    # Kirim cursor + conn ke inventory_change
                    inventory_change(name, barcode, quantity, conn=conn, cursor=cursor)

                    imported_rows += 1

                except Exception as e:
                    print(f"[ERROR] Gagal update/insert: {name}, {barcode}, {quantity} | {e}")

            # Progress Bar
            progress = int((index + 1) / total_rows * 100)
            print(f"\rImporting: {progress}% ({index + 1}/{total_rows})", end="")

        conn.commit()
        print("\nImport selesai!")

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[ERROR] Gagal import: {e}")
        raise

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return imported_rows
