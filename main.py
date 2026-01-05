import sqlite3
import time
import random
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, status, Depends, Response, Cookie, Header
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jose import JWTError, jwt
from authlib.integrations.starlette_client import OAuth
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

app = FastAPI()

# ==========================================
# 1. 中間件與安全性設定 (Middleware & Security)
# ==========================================

# 注意：SessionMiddleware 必須在 OAuth 初始化之前加入
app.add_middleware(SessionMiddleware, secret_key="your-session-secret")

# JWT 設定
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"

# Google OAuth 設定
oauth = OAuth()
oauth.register(
    name='google',
    client_id='688041078983-v70vdok09qt31jdan7ag5lpap1789pi3.apps.googleusercontent.com',
    client_secret='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', # 建議改用 os.getenv 讀取
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# ==========================================
# 2. 資料庫初始化 (Database setup)
# ==========================================

DB_FILE = 'data.db'
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

def init_db():
    # 建立表格
    cursor.execute('''CREATE TABLE IF NOT EXISTS customer 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, password INTEGER NOT NULL, level INTEGER NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS product 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT, whosProductId INTEGER NOT NULL, value INTEGER NOT NULL, image_url TEXT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS purchase 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, customerId INTEGER NOT NULL, productId INTEGER NOT NULL, time INTEGER NOT NULL, count INTEGER NOT NULL)''')
    conn.commit()

    # 預設資料
    cursor.execute("SELECT COUNT(*) FROM customer")
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO customer (name, password, level) VALUES (?,?,?)', [('admin', 1234, 0), ('com', 321, 1)])
    
    cursor.execute("SELECT COUNT(*) FROM product")
    if cursor.fetchone()[0] == 0:
        cursor.executemany('INSERT INTO product (name, description, whosProductId, value, image_url) VALUES (?,?,?,?,?)', 
                           [('瓜', "老闆這瓜保熟嗎", 1, 100, None), ('T91步槍', None, 1, 67890, None)])
    conn.commit()

init_db()

# ==========================================
# 3. 工具函式 (Helper Functions)
# ==========================================

def create_access_token(data: dict):
    to_encode = data.copy()
    # 設定超長過期時間 (原本邏輯)
    expire = datetime.now(timezone.utc) + timedelta(minutes=60 * 24 * 365 * 100)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供認證 Token")
    
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        level: int = payload.get("level")
        if user_id is None:
            raise HTTPException(status_code=401, detail="無效的 Token")
        return {"user_id": user_id, "level": level}
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 已過期或無效")

# ==========================================
# 4. 資料結構 (Pydantic Models)
# ==========================================

class LoginData(BaseModel):
    name: str
    password: int

class RegisterData(BaseModel):
    name: str
    password: int

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    price: int
    image_url: Optional[str] = None

class ProductUpdate(BaseModel):
    name: str
    description: Optional[str] = None
    price: int
    image_url: Optional[str] = None

class PurchaseRequest(BaseModel):
    product_id: int
    count: int

# ==========================================
# 5. 靜態檔案路由 (Static & HTML Files)
# ==========================================

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root(): return FileResponse('html/index.html')

@app.get("/home")
def get_home(): return FileResponse('html/home.html')

@app.get("/manager")
def get_manager(): return FileResponse('html/manager.html')

@app.get("/addProduct.html")
def addProduct_page(): return FileResponse('html/addProduct.html')

@app.get("/manager_user.html")
def manager_user_page(): return FileResponse('html/manager_user.html')

@app.get("/purchase_record.html")
def purchase_record_page(): return FileResponse('html/purchase_record.html')

@app.get("/buy.html")
def buy_page(): return FileResponse('html/buy.html')

@app.get("/updateProduct.html")
def updateProduct_page(): return FileResponse('html/updateProduct.html')

# ==========================================
# 6. 使用者與認證 API (User & Auth)
# ==========================================

@app.post("/register")
def register(data: RegisterData):
    try:
        cursor.execute("SELECT id FROM customer WHERE name = ?", (data.name,))
        if cursor.fetchone():
            return {"sta": 0, "message": "帳號已存在"}
        cursor.execute("INSERT INTO customer (name, password, level) VALUES (?, ?, ?)", (data.name, data.password, 1))
        conn.commit()
        return {"sta": 1, "message": "註冊成功！"}
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"伺服器錯誤: {str(e)}"}

@app.post("/login")
def login(data: LoginData):
    try:
        cursor.execute("SELECT id, name, password, level FROM customer WHERE name = ? AND password = ?", (data.name, data.password))
        user = cursor.fetchone()
        if not user:
            return {"sta": 0, "message": "名字或密碼錯誤"}
        access_token = create_access_token(data={"user_id": user[0], "level": user[3]})
        return {"level": user[3], "sta": 1, "token_access": access_token, "id": user[0]}
    except Exception as e:
        return {"sta": 0, "message": f"伺服器出錯: {str(e)}"}

# --- Google OAuth ---

@app.get("/login/google")
async def login_google(request: Request):
    redirect_uri = "http://127.0.0.1:8000/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/auth/google/callback")
async def auth_google(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get('userinfo')
    if user_info:
        email = user_info['email']
        cursor.execute("SELECT id, level FROM customer WHERE name = ?", (email,))
        user = cursor.fetchone()
        if not user:
            cursor.execute("INSERT INTO customer (name, password, level) VALUES (?, ?, ?)", (email, 0, 1))
            conn.commit()
            cursor.execute("SELECT id, level FROM customer WHERE name = ?", (email,))
            user = cursor.fetchone()
        access_token = create_access_token(data={"user_id": user[0], "level": user[1]})
        response = Response(status_code=302)
        response.headers["Location"] = f"/?token={access_token}"
        return response
    return {"sta": 0, "message": "Google 驗證失敗"}

# ==========================================
# 7. 商品管理 API (Product Management)
# ==========================================

@app.get("/getProducts")
def get_products(user_data: dict = Depends(get_current_user)):
    cursor.execute("SELECT id, name, description, whosProductId, value, image_url FROM product")
    rows = cursor.fetchall()
    return {"status": "success", "data": [{"id": r[0], "name": r[1], "description": r[2], "seller_id": r[3], "price": r[4], "image_url": r[5]} for r in rows]}

@app.post("/addProduct")
def add_product(item: ProductCreate, user_data: dict = Depends(get_current_user)):
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail="權限不足")
    try:
        cursor.execute("INSERT INTO product (name, description, whosProductId, value, image_url) VALUES (?, ?, ?, ?, ?)",
                       (item.name, item.description, user_data["user_id"], item.price, item.image_url))
        conn.commit()
        return {"sta": 1, "message": f"商品 '{item.name}' 上架成功！"}
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"上架失敗: {str(e)}"}

@app.put("/updateProduct/{product_id}")
def update_product(product_id: int, item: ProductUpdate, user_data: dict = Depends(get_current_user)):
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail="權限不足")
    try:
        cursor.execute("UPDATE product SET name=?, description=?, value=?, image_url=? WHERE id=?", 
                       (item.name, item.description, item.price, item.image_url, product_id))
        if cursor.rowcount == 0: return {"sta": 0, "message": "找不到該商品"}
        conn.commit()
        return {"sta": 1, "message": "商品更新成功"}
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"更新失敗: {str(e)}"}

@app.delete("/deleteProduct/{product_id}")
def delete_product(product_id: int, user_data: dict = Depends(get_current_user)):
    if user_data.get("level") != 0:
        raise HTTPException(status_code=403, detail="權限不足")
    try:
        cursor.execute("DELETE FROM product WHERE id = ?", (product_id,))
        conn.commit()
        return {"sta": 1, "message": "商品已成功刪除"}
    except Exception as e:
        return {"sta": 0, "message": f"刪除失敗: {str(e)}"}

# ==========================================
# 8. 交易紀錄與會員管理 API (Admin & History)
# ==========================================

@app.post("/buyProduct")
def buy_product(req: PurchaseRequest, user_data: dict = Depends(get_current_user)):
    cursor.execute("SELECT name FROM product WHERE id = ?", (req.product_id,))
    product = cursor.fetchone()
    if not product: raise HTTPException(status_code=404, detail="商品不存在")
    try:
        cursor.execute("INSERT INTO purchase (customerId, productId, time, count) VALUES (?, ?, ?, ?)",
                       (user_data["user_id"], req.product_id, int(time.time()), req.count))
        conn.commit()
        return {"sta": 1, "message": f"購買成功：{product[0]} x {req.count}"}
    except Exception as e:
        conn.rollback()
        return {"sta": 0, "message": f"資料庫寫入失敗: {str(e)}"}

@app.get("/getPurchaseHistory")
def get_purchase_history(user_data: dict = Depends(get_current_user)):
    user_id, level = user_data["user_id"], user_data["level"]
    query = '''SELECT p.id, c.name, pr.name, pr.value, p.count, p.time 
               FROM purchase p JOIN customer c ON p.customerId = c.id JOIN product pr ON p.productId = pr.id'''
    if level != 0:
        query += " WHERE p.customerId = ?"
        cursor.execute(query, (user_id,))
    else:
        cursor.execute(query)
    
    rows = cursor.fetchall()
    return {"level": level, "data": [{"order_id": r[0], "user_name": r[1], "product": r[2], "price": r[3], "count": r[4], "time": r[5]} for r in rows]}

@app.get("/getCustomers")
def get_customers(user_data: dict = Depends(get_current_user)):
    if user_data.get("level") != 0: raise HTTPException(status_code=403, detail="權限不足")
    cursor.execute("SELECT id, name, level FROM customer")
    rows = cursor.fetchall()
    return {"sta": 1, "data": [{"id": r[0], "name": r[1], "level": r[2]} for r in rows]}

@app.delete("/deleteCustomer/{user_id}")
def delete_customer(user_id: int, user_data: dict = Depends(get_current_user)):
    if user_data.get("level") != 0: raise HTTPException(status_code=403, detail="權限不足")
    if user_id == user_data.get("user_id"): return {"sta": 0, "message": "你不能刪除你自己！"}
    try:
        cursor.execute("DELETE FROM customer WHERE id = ?", (user_id,))
        conn.commit()
        return {"sta": 1, "message": "會員已刪除"}
    except Exception as e:
        return {"sta": 0, "message": str(e)}