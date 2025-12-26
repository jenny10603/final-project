import sqlite3
import time
import random
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, status, Depends, Response, Cookie, Header
from pydantic import BaseModel
from fastapi.responses import FileResponse
from jose import JWTError, jwt
from fastapi.staticfiles import StaticFiles

app = FastAPI()
# 資料庫連線
DB_FILE = 'data.db'
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

# JWT 設定
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# --- 1. 初始化資料庫 ---
cursor.execute('''
    CREATE TABLE IF NOT EXISTS customer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        password INTEGER NOT NULL,
        level INTEGER NOT NULL
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
        customers = [('admin', 1234, 0), ('com', 321, 1)]
        cursor.executemany('INSERT INTO customer (name, password, level) VALUES (?,?,?)', customers)
    
    cursor.execute("SELECT COUNT(*) FROM product")
    if cursor.fetchone()[0] == 0:
        products = [('瓜', "老闆這瓜保熟嗎", 1, 100), ('T91步槍', None, 1, 67890)]
        cursor.executemany('INSERT INTO product (name, description, whosProductId, value) VALUES (?,?,?,?)', products)
    conn.commit()

init_data()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(authorization: str = Header(None)):
    # 1. 檢查有沒有 Header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供認證 Token")
    
    # 2. 取得 Token 字串 (去掉 "Bearer " 這七個字)
    token = authorization.split(" ")[1]
    
    try:
        # 3. 解碼 Token
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        
        if user_id is None:
            raise HTTPException(status_code=401, detail="無效的 Token")
        
        return {"user_id": user_id}
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 已過期或無效")
# --- 2. 資料結構 (Pydantic Models) ---

class LoginData(BaseModel):
    name: str
    password: int

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: int

class PurchaseRequest(BaseModel):
    product_id: int
    count: int

# --- 3. 靜態檔案 ---
# 提醒：若無 static 資料夾，請手動建立或註解掉此行
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 4. API 路徑 (已去除重複) ---

@app.get("/")
def root():
    return FileResponse('html/index.html')

@app.get("/home")
def get_home():
    return FileResponse('html/home.html')

@app.get("/manager")
def get_home():
    return FileResponse('html/manager.html')

@app.post("/login")
def login(data: LoginData):
    try:
        cursor.execute("SELECT id, name, password, level FROM customer WHERE name = ? AND password = ?", (data.name, data.password))
        user = cursor.fetchone()
        
        if not user:
            # 帳密錯，回傳你指定的 sta: 0
            return {"sta": 0, "message": "名字或密碼錯誤"}
        
        access_token = create_access_token(data={"user_id": user[0]})
        
        return {
            "level":user[3],
            "sta": 1,
            "token_access": access_token, 
            "id": user[0],
        }
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"伺服器出錯: {str(e)}"}


@app.get("/getProducts")
def get_products(user_id: int = Depends(get_current_user)):
    cursor.execute("SELECT id, name, description, whosProductId, value FROM product")
    rows = cursor.fetchall()
    return {
        "status": "success",
        "data": [{"id": r[0], "name": r[1], "description": r[2], "seller_id": r[3], "price": r[4]} for r in rows]
    }

@app.post("/buyProduct")
def buy_product(
    req: PurchaseRequest, 
    user_id: int = Depends(get_current_user) # 關鍵：這行會自動執行上面的驗證
):
    # 此時，user_id 是從 Token 裡面「解密」出來的，絕對安全！
    
    # 檢查商品是否存在
    cursor.execute("SELECT name FROM product WHERE id = ?", (req.product_id,))
    product = cursor.fetchone()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    try:
        # 寫入購買紀錄
        real_user_id = user_id["user_id"]
        current_time = int(time.time())
        cursor.execute('''
            INSERT INTO purchase (customerId, productId, time, count) 
            VALUES (?, ?, ?, ?)
        ''', (real_user_id, req.product_id, current_time, req.count))
        
        conn.commit()
        
        return {
            "sta": 1,
            "message": f"購買成功：{product[0]} x {req.count}",
            "user_id": user_id  # 可以回傳確認是誰買的
        }
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"資料庫寫入失敗: {str(e)}"}
    
@app.get("/getPurchaseHistory")
def get_purchase_history(
    user_id: int = Depends(get_current_user) # 關鍵：這行會自動執行上面的驗證
):
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

@app.post("/addProduct")
def add_product(
    item: ProductCreate, 
    user_data: dict = Depends(get_current_user)  # 關鍵：驗證身分並取得 Token 內容
):
    # 從 Token 資料中取出 user_id
    seller_id = user_data["user_id"]
    
    #"權限不足，您不是賣家"
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail=user_data.get("level"))

    try:
        # 將商品資訊寫入資料庫
        cursor.execute('''
            INSERT INTO product (name, description, whosProductId, value) 
            VALUES (?, ?, ?, ?)
        ''', (item.name, item.description, seller_id, item.price))
        
        conn.commit()
        
        return {
            "sta": 1, 
            "message": f"商品 '{item.name}' 上架成功！",
            "seller_id": seller_id
        }
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"上架失敗: {str(e)}"}