import sqlite3
import time
import random
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# 資料庫連線
DB_FILE = 'data.db'
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

# --- 1. 初始化資料庫 ---
cursor.execute('''
    CREATE TABLE IF NOT EXISTS customer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        password INTEGER NOT NULL,
        level INTEGER NOT NULL,
        key INTEGER NOT NULL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS product (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        whosProductId INTEGER NOT NULL,
        value INTEGER NOT NULL
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS purchase (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customerId INTEGER NOT NULL,
        productId INTEGER NOT NULL,
        time INTEGER NOT NULL,
        count INTEGER NOT NULL
    )
''')
conn.commit()

def init_data():
    cursor.execute("SELECT COUNT(*) FROM customer")
    if cursor.fetchone()[0] == 0:
        customers = [('老王賣瓜', 1234, 0, 12345), ('小明買家', 321, 1, 67890)]
        cursor.executemany('INSERT INTO customer (name, password, level, key) VALUES (?,?,?,?)', customers)
    
    cursor.execute("SELECT COUNT(*) FROM product")
    if cursor.fetchone()[0] == 0:
        products = [('瓜', "老闆這瓜堡熟嗎", 1, 100), ('T91步槍', None, 1, 67890)]
        cursor.executemany('INSERT INTO product (name, description, whosProductId, value) VALUES (?,?,?,?)', products)
    conn.commit()

init_data()

# --- 2. 資料結構 (Pydantic Models) ---

class LoginData(BaseModel):
    name: str
    password: int

class ProductCreate(BaseModel):
    user_id: int
    key: int
    name: str
    description: Optional[str] = None
    price: int

class PurchaseRequest(BaseModel):
    customer_id: int
    key: int
    product_id: int
    count: int

# --- 3. 靜態檔案 ---
# 提醒：若無 static 資料夾，請手動建立或註解掉此行
# app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 4. API 路徑 (已去除重複) ---

@app.get("/")
def root():
    return FileResponse('index.html')

@app.get("/home")
def get_home():
    return FileResponse('home.html')

@app.post("/login")
def login(data: LoginData):
    try:
        cursor.execute("SELECT id FROM customer WHERE name = ? AND password = ?", (data.name, data.password))
        user = cursor.fetchone()
        
        if not user:
            # 帳密錯，回傳你指定的 sta: 0
            return {"sta": 0, "message": "名字或密碼錯誤"}
        
        user_id = user[0]
        new_key = random.randint(10000, 99999)

        cursor.execute("UPDATE customer SET key = ? WHERE id = ?", (new_key, user_id))
        conn.commit()
        
        return {
            "sta": 1,
            "message": "登入成功，Key 已更新", 
            "id": user_id,
            "key": new_key
        }
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"伺服器出錯: {str(e)}"}

@app.get("/getProducts")
def get_products():
    cursor.execute("SELECT id, name, description, whosProductId, value FROM product")
    rows = cursor.fetchall()
    return {
        "status": "success",
        "data": [{"id": r[0], "name": r[1], "description": r[2], "seller_id": r[3], "price": r[4]} for r in rows]
    }

@app.post("/buyProduct")
def buy_product(req: PurchaseRequest):
    # 驗證買家
    cursor.execute("SELECT id FROM customer WHERE id = ? AND key = ?", (req.customer_id, req.key))
    if not cursor.fetchone():
        raise HTTPException(status_code=401, detail="身分驗證失敗")

    # 檢查商品
    cursor.execute("SELECT name FROM product WHERE id = ?", (req.product_id,))
    product = cursor.fetchone()
    if not product:
        raise HTTPException(status_code=404, detail="找不到該商品")

    try:
        current_time = int(time.time())
        cursor.execute('''
            INSERT INTO purchase (customerId, productId, time, count) 
            VALUES (?, ?, ?, ?)
        ''', (req.customer_id, req.product_id, current_time, req.count))
        conn.commit()
        
        return {
            "status": "success",
            "sta": 1,
            "message": f"成功購買 {req.count} 個 {product[0]}",
            "time": datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": str(e)}

@app.get("/getPurchaseHistory")
def get_purchase_history():
    cursor.execute('''
        SELECT p.id, c.name, pr.name, p.count, p.time 
        FROM purchase p
        JOIN customer c ON p.customerId = c.id
        JOIN product pr ON p.productId = pr.id
    ''')
    rows = cursor.fetchall()
    return {
        "data": [
            {"order_id": r[0], "customer": r[1], "product": r[2], "count": r[3], "time": r[4]} 
            for r in rows
        ]
    }