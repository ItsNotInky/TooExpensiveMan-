# 🥑 PantryOS — Smart Grocery Tracker

> A fully-featured Progressive Web App for managing your grocery inventory with expiry tracking, receipt scanning, spending analytics, and cloud sync.

![PantryOS](https://img.shields.io/badge/PantryOS-v2.0-00d4b1?style=flat-square)
![PWA](https://img.shields.io/badge/PWA-Ready-7c6af7?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-success?style=flat-square)

---

## ✨ Features

| Feature | Description |
|---|---|
| 📦 **Inventory Management** | Add, edit, delete items with category, quantity, unit, price |
| ⏱ **Expiry Countdown** | Real-time days-remaining counter with color-coded urgency |
| ⚠️ **Expiry Warnings** | Dashboard alerts for items expiring within your threshold |
| 💰 **Price Tracking** | Per-item pricing with pantry total value calculation |
| 📊 **Spending Analytics** | Charts by time period, category, and waste analysis |
| 📷 **Receipt Scanning** | OCR via Tesseract.js (browser) or pytesseract (server) |
| 🛒 **Shopping List** | Manual + auto-generated lists from expired/expiring items |
| ☁️ **Cloud Sync** | Firebase Firestore integration (free tier) |
| 📱 **PWA** | Install on mobile/desktop, works offline |
| 🌙 **Dark Theme** | Beautiful dark UI with teal/purple accents |

---

## 🚀 Quick Start

### Option A — GitHub Pages (Static, No Backend)

1. Fork this repository
2. Go to **Settings → Pages → Source: Deploy from branch → main**
3. Visit `https://yourusername.github.io/pantryos/`
4. Data stores in **localStorage** by default

### Option B — Python Backend (Full Features + Server OCR)

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/pantryos.git
cd pantryos

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Tesseract (for server-side OCR)
# macOS:    brew install tesseract
# Ubuntu:   sudo apt install tesseract-ocr
# Windows:  https://github.com/UB-Mannheim/tesseract/wiki

# 5. Run
python app.py

# Visit http://localhost:5000
```

### Option C — Deploy to Render (Free Cloud Hosting)

1. Create account at [render.com](https://render.com)
2. New → Web Service → Connect your GitHub repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Free tier available!

---

## ☁️ Cloud Sync Setup (Firebase)

1. Go to [console.firebase.google.com](https://console.firebase.google.com)
2. Create a new project
3. Go to **Firestore Database → Create database** (Start in test mode)
4. Go to **Project Settings → Your apps → Add app (Web)**
5. Copy your config object
6. In PantryOS → **Settings → Cloud Sync** → Paste config → Click Connect

**Free Tier Limits:** 1GB storage, 50K reads/day, 20K writes/day — more than enough!

---

## 📷 Receipt Scanning

### Browser OCR (GitHub Pages / Static)
- Uses [Tesseract.js](https://tesseract.projectnaptha.com/) loaded from CDN
- Processes images entirely in the browser
- Works offline after first load

### Server OCR (Python Backend)
```bash
# Install Tesseract binary first (see above)
# Then use the /api/ocr endpoint

curl -X POST http://localhost:5000/api/ocr \
  -F "image=@receipt.jpg"
```

---

## 🛠️ API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/items` | List all items |
| POST | `/api/items` | Create item |
| GET | `/api/items/:id` | Get single item |
| PUT | `/api/items/:id` | Update item |
| DELETE | `/api/items/:id` | Delete item |
| GET | `/api/items/expiry/warnings` | Get expiring/expired items |
| GET | `/api/shopping` | Get shopping list |
| POST | `/api/shopping` | Add to shopping list |
| POST | `/api/shopping/auto-generate` | Auto-generate from expired items |
| GET | `/api/analytics` | Spending analytics |
| POST | `/api/ocr` | OCR receipt image |
| GET | `/api/export` | Export all data as JSON |
| POST | `/api/import` | Import from JSON export |

### Example: Add an Item
```json
POST /api/items
{
  "name": "Organic Milk",
  "category": "Dairy",
  "quantity": 2,
  "unit": "L",
  "price": 4.99,
  "purchaseDate": "2024-01-15",
  "expiryDate": "2024-01-22",
  "store": "Whole Foods"
}
```

---

## 📱 PWA Installation

**iPhone/iPad:** Safari → Share → Add to Home Screen  
**Android:** Chrome → Menu → Add to Home Screen  
**Desktop:** Chrome/Edge → Address bar → Install icon  

---

## 🎨 Tech Stack

| Layer | Technology |
|---|---|
| Frontend | HTML5, CSS3 (custom properties), Vanilla JS |
| Charts | Chart.js 4.x |
| OCR (browser) | Tesseract.js 4.x |
| OCR (server) | pytesseract + Pillow |
| Backend | Python Flask 3.x |
| Database | SQLite (dev) / PostgreSQL (prod) via SQLAlchemy |
| Cloud | Firebase Firestore |
| PWA | Service Worker + Web App Manifest |
| Hosting | GitHub Pages / Render / Railway |
| Fonts | Syne + JetBrains Mono (Google Fonts) |

---

## 📁 Project Structure

```
pantryos/
├── index.html          # Main PWA frontend (self-contained)
├── sw.js               # Service Worker (offline support)
├── manifest.json       # PWA manifest
├── app.py              # Python Flask backend
├── requirements.txt    # Python dependencies
├── generate_icons.py   # PWA icon generator
├── icons/              # PWA icons (generate or replace)
│   ├── icon-72.png
│   ├── icon-96.png
│   ├── icon-128.png
│   ├── icon-192.png
│   └── icon-512.png
└── README.md
```

---

## ⚙️ Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | Server port |
| `SECRET_KEY` | `dev-secret` | Flask secret key |
| `DATABASE_URL` | `sqlite:///pantryos.db` | Database URL |
| `FLASK_DEBUG` | `true` | Debug mode |

---

## 🤝 Contributing

PRs welcome! Please:
1. Fork the repo
2. Create a feature branch
3. Submit a PR with description

---

## 📄 License

MIT License — free for personal and commercial use.

---

*Built with ❤️ — Keep your pantry organized!*
