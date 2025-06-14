import io
import os
import pandas as pd
from datetime import datetime

def export_products_to_excel(products):
    df = pd.DataFrame(products)

    if 'barcode' in df.columns:
        df['barcode'] = df['barcode'].apply(lambda x: f"'{str(x)}" if pd.notnull(x) else x)

    if 'id' in df.columns:
        df = df.drop(columns=['id'])

    # Buat file Excel di memory (RAM) tanpa file fisik
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)

    return output
