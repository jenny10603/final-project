import sqlite3
import time  # 用於記錄購買時間
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import time  # 用於紀錄 Unix 時間戳
from datetime import datetime
import random
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

DB_FILE = 'data.db'
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()


# 1. 建立表格 (Customer, Product & Purchase)
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

# 完善：建立購買紀錄表
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

# --- 資料結構定義 (Pydantic Models) ---

class ProductCreate(BaseModel):
    user_id: int
    key: int
    name: str
    description: Optional[str] = None
    price: int

# 新增：購買請求的結構
class PurchaseRequest(BaseModel):
    customer_id: int  # 買家 ID
    key: int          # 買家 Key (驗證用)
    product_id: int   # 商品 ID
    count: int        # 購買數量

# --- API 路徑 ---

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
def root():
    return FileResponse('index.html')

@app.get("/getCustomers")
def get_customers():
    cursor.execute("SELECT id, name, password, level, key FROM customer")
    rows = cursor.fetchall()
    return {"data": [{"id": r[0], "name": r[1], "password": r[2], "level": r[3], "key": r[4]} for r in rows]}

# 取得所有商品
@app.get("/getProducts")
def get_products():
    cursor.execute("SELECT id, name, description, whosProductId, value FROM product")
    rows = cursor.fetchall()
    return {
        "status": "success",
        "data": [{"id": r[0], "name": r[1], "description": r[2], "seller_id": r[3], "price": r[4]} for r in rows]
    }

# 定義一個模型來接收 JSON 資料
class LoginData(BaseModel):
    name: str
    password: int

@app.post("/login")
def login(data: LoginData):
    # 1. 先驗證帳號密碼
    cursor.execute(
        "SELECT id FROM customer WHERE name = ? AND password = ?", 
        (data.name, data.password)
    )
    user = cursor.fetchone()
    
    if not user:
        raise HTTPException(status_code=401, detail="名字或密碼錯誤")
    
    user_id = user[0]

    # 2. 產生新的隨機 Key (假設是 5 位數的隨機數)
    new_key = random.randint(10000, 99999)

    try:
        # 3. 更新資料庫中該使用者的 Key
        cursor.execute(
            "UPDATE customer SET key = ? WHERE id = ?", 
            (new_key, user_id)
        )
        conn.commit()  # 記得要 commit 才會儲存變更
        
        return {
            "message": "登入成功，Key 已更新", 
            "id": user_id,
            "key": new_key  # 回傳新的 Key 給前端
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail="更新 Key 時發生錯誤")

# 上架商品
@app.post("/addProduct")
def add_product(item: ProductCreate):
    cursor.execute("SELECT level FROM customer WHERE id = ? AND key = ?", (item.user_id, item.key))
    user = cursor.fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="身分驗證失敗")
    if user[0] != 0:
        raise HTTPException(status_code=403, detail="只有賣家可以上架商品")

    cursor.execute('INSERT INTO product (name, description, whosProductId, value) VALUES (?,?,?,?)', 
                   (item.name, item.description, item.user_id, item.price))
    conn.commit()
    return {"status": "success", "message": f"商品 '{item.name}' 上架成功"}

# --- 新增功能：購買商品 ---

@app.post("/buyProduct")
def buy_product(req: PurchaseRequest):
    # 1. 驗證買家身分 (ID 與 Key 是否匹配)
    cursor.execute("SELECT id FROM customer WHERE id = ? AND key = ?", (req.customer_id, req.key))
    customer = cursor.fetchone()
    if not customer:
        raise HTTPException(status_code=401, detail="身分驗證失敗，無法購買")

    # 2. 檢查商品是否存在
    cursor.execute("SELECT name FROM product WHERE id = ?", (req.product_id,))
    product = cursor.fetchone()
    if not product:
        raise HTTPException(status_code=404, detail="找不到該商品")

    try:
        # 3. 寫入購買紀錄 (使用當前 Unix 時間戳)
        current_time = int(time.time())
        cursor.execute('''
            INSERT INTO purchase (customerId, productId, time, count) 
            VALUES (?, ?, ?, ?)
        ''', (req.customer_id, req.product_id, current_time, req.count))
        
        conn.commit()
        return {
            "status": "success",
            "message": f"成功購買 {req.count} 個 {product[0]}",
            "timestamp": current_time
        }
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"購買失敗: {str(e)}")

# --- 新增功能：查看所有購買紀錄 ---

@app.get("/getPurchaseHistory")
def get_purchase_history():
    # 使用 JOIN 同時抓取客戶名稱和商品名稱，讓資料更好讀
    cursor.execute('''
        SELECT p.id, c.name, pr.name, p.count, p.time 
        FROM purchase p
        JOIN customer c ON p.customerId = c.id
        JOIN product pr ON p.productId = pr.id
    ''')
    rows = cursor.fetchall()
    
    history = []
    for r in rows:
        history.append({
            "purchase_id": r[0],
            "customer_name": r[1],
            "product_name": r[2],
            "quantity": r[3],
            "time": r[4]
        })
    return {"status": "success", "data": history}


class PurchaseRequest(BaseModel):
    customer_id: int  # 買家 ID
    key: int          # 買家 Key (驗證身分用)
    product_id: int   # 想要購買的商品 ID
    count: int        # 購買數量

# 2. 實作購買 API
@app.post("/buyProduct")
def buy_product(req: PurchaseRequest):
    # 第一步：身分驗證 (檢查 ID 與 Key 是否在 customer 表中匹配)
    cursor.execute(
        "SELECT id FROM customer WHERE id = ? AND key = ?", 
        (req.customer_id, req.key)
    )
    customer = cursor.fetchone()
    
    if not customer:
        raise HTTPException(status_code=401, detail="身分驗證失敗，ID 或 Key 錯誤")

    # 第二步：檢查商品是否存在
    cursor.execute("SELECT name, value FROM product WHERE id = ?", (req.product_id,))
    product = cursor.fetchone()
    
    if not product:
        raise HTTPException(status_code=404, detail="找不到該商品")

    try:
        # 第三步：紀錄購買資訊
        current_time = int(time.time())  # 取得當前 Unix 時間
        readable_time = datetime.fromtimestamp(current_time).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute('''
            INSERT INTO purchase (customerId, productId, time, count) 
            VALUES (?, ?, ?, ?)
        ''', (req.customer_id, req.product_id, current_time, req.count))
        
        conn.commit()  # 提交變更到資料庫
        
        return {
            "status": "success",
            "message": f"成功購買 {req.count} 個 {product[0]}",
            "details": {
                "buyer_id": req.customer_id,
                "product_id": req.product_id,
                "total_count": req.count,
                "time": current_time
            }
        }
    except Exception as e:
        conn.rollback()  # 發生錯誤時回滾，確保資料庫安全
        raise HTTPException(status_code=500, detail=f"購買過程發生錯誤: {str(e)}")

# 3. 額外功能：查看購買紀錄 (方便你驗證結果)
@app.get("/getPurchaseHistory")
def get_purchase_history():
    # 使用 JOIN 同時抓取客戶名稱與商品名稱
    query = '''
        SELECT p.id, c.name, pr.name, p.count, p.time 
        FROM purchase p
        JOIN customer c ON p.customerId = c.id
        JOIN product pr ON p.productId = pr.id
    '''
    cursor.execute(query)
    rows = cursor.fetchall()
    
    return {
        "data": [
            {"order_id": r[0], "customer": r[1], "product": r[2], "count": r[3], "time": r[4]} 
            for r in rows
        ]
    }