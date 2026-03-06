"""
PantryOS - Python Flask Backend
================================
Optional server backend for PantryOS.
Provides REST API, server-side OCR, and SQLite persistence.
Can be used instead of or alongside the static GitHub Pages version.

Run: python app.py
API base: http://localhost:5000/api
"""

import os
import json
import uuid
import logging
from datetime import datetime, date, timedelta
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS

# Optional: pytesseract for server-side OCR
try:
    import pytesseract
    from PIL import Image
    import io
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("[WARNING] pytesseract/Pillow not installed. OCR endpoint unavailable.")
    print("          Install with: pip install pytesseract Pillow")

# Optional: SQLite via SQLAlchemy
try:
    from flask_sqlalchemy import SQLAlchemy
    from sqlalchemy.exc import SQLAlchemyError
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    print("[WARNING] Flask-SQLAlchemy not installed. Using file-based storage.")
    print("          Install with: pip install Flask-SQLAlchemy")

# ─── App Setup ─────────────────────────────────────────────
app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-pantryos-2024')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max upload
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'sqlite:///pantryos.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ─── CORS ──────────────────────────────────────────────────
CORS(app, resources={r"/api/*": {"origins": ["http://localhost:*", "https://*.github.io"]}})

# ─── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('pantryos')

# ─── Database Models (if SQLAlchemy available) ─────────────
if DB_AVAILABLE:
    db = SQLAlchemy(app)

    class GroceryItem(db.Model):
        __tablename__ = 'grocery_items'
        id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
        name = db.Column(db.String(200), nullable=False)
        category = db.Column(db.String(100), default='Other')
        store = db.Column(db.String(200))
        quantity = db.Column(db.Float, default=1.0)
        unit = db.Column(db.String(50), default='units')
        price = db.Column(db.Float, default=0.0)
        purchase_date = db.Column(db.String(10))
        expiry_date = db.Column(db.String(10))
        notes = db.Column(db.Text)
        added_at = db.Column(db.DateTime, default=datetime.utcnow)
        updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
        user_id = db.Column(db.String(64), default='default')

        def to_dict(self):
            return {
                'id': self.id,
                'name': self.name,
                'category': self.category,
                'store': self.store or '',
                'quantity': self.quantity,
                'unit': self.unit,
                'price': self.price,
                'purchaseDate': self.purchase_date,
                'expiryDate': self.expiry_date,
                'notes': self.notes or '',
                'addedAt': self.added_at.isoformat() if self.added_at else None,
                'updatedAt': self.updated_at.isoformat() if self.updated_at else None,
            }

    class ShoppingItem(db.Model):
        __tablename__ = 'shopping_items'
        id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
        name = db.Column(db.String(200), nullable=False)
        category = db.Column(db.String(100))
        quantity = db.Column(db.Integer, default=1)
        unit = db.Column(db.String(50))
        estimated_price = db.Column(db.Float, default=0.0)
        priority = db.Column(db.String(20), default='medium')
        checked = db.Column(db.Boolean, default=False)
        added_at = db.Column(db.DateTime, default=datetime.utcnow)
        user_id = db.Column(db.String(64), default='default')

        def to_dict(self):
            return {
                'id': self.id,
                'name': self.name,
                'category': self.category,
                'quantity': self.quantity,
                'unit': self.unit,
                'estimatedPrice': self.estimated_price,
                'priority': self.priority,
                'checked': self.checked,
                'addedAt': self.added_at.isoformat() if self.added_at else None,
            }

# ─── File-based Storage Fallback ───────────────────────────
DATA_FILE = 'pantryos_data.json'

def load_file_data():
    """Load data from JSON file (fallback when SQLAlchemy not available)."""
    if not os.path.exists(DATA_FILE):
        return {'items': [], 'shopping': []}
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load data file: {e}")
        return {'items': [], 'shopping': []}

def save_file_data(data):
    """Save data to JSON file (fallback)."""
    try:
        # Write to temp file first for atomic operation
        tmp_file = DATA_FILE + '.tmp'
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp_file, DATA_FILE)
    except IOError as e:
        logger.error(f"Failed to save data file: {e}")
        raise

# ─── Validation ────────────────────────────────────────────
def validate_item_data(data, partial=False):
    """Validate grocery item data. Returns (is_valid, errors)."""
    errors = {}

    if not partial or 'name' in data:
        name = data.get('name', '')
        if not isinstance(name, str) or not name.strip():
            errors['name'] = 'Name is required and must be a string'
        elif len(name.strip()) > 200:
            errors['name'] = 'Name must be 200 characters or less'

    if not partial or 'price' in data:
        price = data.get('price', 0)
        try:
            price = float(price)
            if price < 0:
                errors['price'] = 'Price cannot be negative'
            elif price > 999999:
                errors['price'] = 'Price seems unreasonably large'
        except (TypeError, ValueError):
            errors['price'] = 'Price must be a number'

    if not partial or 'quantity' in data:
        qty = data.get('quantity', 1)
        try:
            qty = float(qty)
            if qty <= 0:
                errors['quantity'] = 'Quantity must be greater than 0'
        except (TypeError, ValueError):
            errors['quantity'] = 'Quantity must be a number'

    # Validate dates
    purchase_date = data.get('purchaseDate')
    expiry_date = data.get('expiryDate')

    if purchase_date:
        try:
            datetime.strptime(purchase_date, '%Y-%m-%d')
        except ValueError:
            errors['purchaseDate'] = 'Invalid date format (YYYY-MM-DD required)'

    if expiry_date:
        try:
            exp = datetime.strptime(expiry_date, '%Y-%m-%d')
            if purchase_date:
                purch = datetime.strptime(purchase_date, '%Y-%m-%d')
                if exp < purch:
                    errors['expiryDate'] = 'Expiry date cannot be before purchase date'
        except ValueError:
            errors['expiryDate'] = 'Invalid date format (YYYY-MM-DD required)'

    return len(errors) == 0, errors

# ─── Error Handlers ────────────────────────────────────────
@app.errorhandler(400)
def bad_request(e):
    return jsonify({'error': 'Bad Request', 'message': str(e)}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not Found', 'message': str(e)}), 404

@app.errorhandler(413)
def request_too_large(e):
    return jsonify({'error': 'File Too Large', 'message': 'Maximum upload size is 10MB'}), 413

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal error: {e}")
    return jsonify({'error': 'Internal Server Error', 'message': 'An unexpected error occurred'}), 500

def handle_db_error(f):
    """Decorator to handle database errors gracefully."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {e}", exc_info=True)
            if DB_AVAILABLE:
                db.session.rollback()
            return jsonify({'error': 'Database Error', 'message': str(e)}), 500
    return wrapper

# ─── API Routes ─────────────────────────────────────────────

# --- Health Check ---
@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'version': '2.0.0',
        'ocr': OCR_AVAILABLE,
        'database': DB_AVAILABLE,
        'timestamp': datetime.utcnow().isoformat()
    })

# ─── Grocery Items ──────────────────────────────────────────

@app.route('/api/items', methods=['GET'])
@handle_db_error
def get_items():
    """Get all grocery items with optional filtering."""
    category = request.args.get('category')
    search = request.args.get('search', '').strip().lower()
    sort_by = request.args.get('sort', 'expiry')
    show_expired = request.args.get('showExpired', 'true').lower() == 'true'

    if DB_AVAILABLE:
        query = GroceryItem.query.filter_by(user_id='default')
        if category:
            query = query.filter_by(category=category)
        items = [i.to_dict() for i in query.all()]
    else:
        data = load_file_data()
        items = data.get('items', [])

    # Filter
    if search:
        items = [i for i in items if search in i.get('name','').lower()
                 or search in i.get('category','').lower()
                 or search in i.get('store','').lower()]
    if not show_expired:
        today = date.today().isoformat()
        items = [i for i in items if not i.get('expiryDate') or i['expiryDate'] >= today]
    if category:
        items = [i for i in items if i.get('category') == category]

    # Sort
    if sort_by == 'name':
        items.sort(key=lambda i: i.get('name','').lower())
    elif sort_by == 'price':
        items.sort(key=lambda i: i.get('price', 0), reverse=True)
    elif sort_by == 'date':
        items.sort(key=lambda i: i.get('addedAt',''), reverse=True)
    else:  # expiry
        def expiry_key(item):
            ed = item.get('expiryDate')
            if not ed:
                return '9999-99-99'
            return ed
        items.sort(key=expiry_key)

    # Compute stats
    total_value = sum(i.get('price', 0) * i.get('quantity', 1) for i in items)
    today_str = date.today().isoformat()
    expiring_soon = sum(1 for i in items if i.get('expiryDate') and
                        today_str <= i['expiryDate'] <= (date.today() + timedelta(days=3)).isoformat())
    expired = sum(1 for i in items if i.get('expiryDate') and i['expiryDate'] < today_str)

    return jsonify({
        'items': items,
        'count': len(items),
        'totalValue': round(total_value, 2),
        'expiringSoon': expiring_soon,
        'expired': expired,
    })

@app.route('/api/items', methods=['POST'])
@handle_db_error
def create_item():
    """Create a new grocery item."""
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 400

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Empty request body'}), 400

    is_valid, errors = validate_item_data(data)
    if not is_valid:
        return jsonify({'error': 'Validation Error', 'fields': errors}), 422

    item_id = str(uuid.uuid4().hex)

    if DB_AVAILABLE:
        item = GroceryItem(
            id=item_id,
            name=data['name'].strip()[:200],
            category=data.get('category', 'Other')[:100],
            store=(data.get('store', '') or '')[:200],
            quantity=float(data.get('quantity', 1)),
            unit=(data.get('unit', 'units'))[:50],
            price=float(data.get('price', 0)),
            purchase_date=data.get('purchaseDate') or date.today().isoformat(),
            expiry_date=data.get('expiryDate'),
            notes=(data.get('notes', '') or '')[:1000],
        )
        db.session.add(item)
        db.session.commit()
        result = item.to_dict()
    else:
        file_data = load_file_data()
        item = {
            'id': item_id,
            'name': data['name'].strip()[:200],
            'category': data.get('category', 'Other'),
            'store': data.get('store', ''),
            'quantity': float(data.get('quantity', 1)),
            'unit': data.get('unit', 'units'),
            'price': float(data.get('price', 0)),
            'purchaseDate': data.get('purchaseDate') or date.today().isoformat(),
            'expiryDate': data.get('expiryDate'),
            'notes': data.get('notes', ''),
            'addedAt': datetime.utcnow().isoformat(),
            'updatedAt': datetime.utcnow().isoformat(),
        }
        file_data['items'].append(item)
        save_file_data(file_data)
        result = item

    logger.info(f"Created item: {result['name']} (id={result['id']})")
    return jsonify(result), 201

@app.route('/api/items/<item_id>', methods=['GET'])
@handle_db_error
def get_item(item_id):
    if not item_id or len(item_id) > 64:
        abort(400, 'Invalid item ID')
    if DB_AVAILABLE:
        item = GroceryItem.query.get_or_404(item_id)
        return jsonify(item.to_dict())
    else:
        data = load_file_data()
        item = next((i for i in data['items'] if i['id'] == item_id), None)
        if not item:
            abort(404, 'Item not found')
        return jsonify(item)

@app.route('/api/items/<item_id>', methods=['PUT'])
@handle_db_error
def update_item(item_id):
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 400

    data = request.get_json()
    is_valid, errors = validate_item_data(data, partial=True)
    if not is_valid:
        return jsonify({'error': 'Validation Error', 'fields': errors}), 422

    if DB_AVAILABLE:
        item = GroceryItem.query.get_or_404(item_id)
        updatable = ['name','category','store','quantity','unit','price','purchase_date','expiry_date','notes']
        field_map = {'purchaseDate':'purchase_date','expiryDate':'expiry_date'}
        for key, value in data.items():
            attr = field_map.get(key, key)
            if attr in updatable:
                setattr(item, attr, value)
        item.updated_at = datetime.utcnow()
        db.session.commit()
        return jsonify(item.to_dict())
    else:
        file_data = load_file_data()
        idx = next((i for i,item in enumerate(file_data['items']) if item['id'] == item_id), None)
        if idx is None:
            abort(404, 'Item not found')
        file_data['items'][idx].update({k:v for k,v in data.items()})
        file_data['items'][idx]['updatedAt'] = datetime.utcnow().isoformat()
        save_file_data(file_data)
        return jsonify(file_data['items'][idx])

@app.route('/api/items/<item_id>', methods=['DELETE'])
@handle_db_error
def delete_item(item_id):
    if DB_AVAILABLE:
        item = GroceryItem.query.get_or_404(item_id)
        name = item.name
        db.session.delete(item)
        db.session.commit()
    else:
        file_data = load_file_data()
        items_before = len(file_data['items'])
        file_data['items'] = [i for i in file_data['items'] if i['id'] != item_id]
        if len(file_data['items']) == items_before:
            abort(404, 'Item not found')
        save_file_data(file_data)
        name = item_id
    logger.info(f"Deleted item: {name}")
    return jsonify({'success': True, 'id': item_id})

# ─── Expiry Warnings ────────────────────────────────────────
@app.route('/api/items/expiry/warnings')
@handle_db_error
def get_expiry_warnings():
    """Get items expiring soon and already expired."""
    days = int(request.args.get('days', 3))
    today = date.today()
    warn_date = (today + timedelta(days=days)).isoformat()
    today_str = today.isoformat()

    if DB_AVAILABLE:
        items = [i.to_dict() for i in GroceryItem.query.filter_by(user_id='default').all()]
    else:
        items = load_file_data().get('items', [])

    expired = [i for i in items if i.get('expiryDate') and i['expiryDate'] < today_str]
    expiring = [i for i in items if i.get('expiryDate') and today_str <= i['expiryDate'] <= warn_date]

    return jsonify({
        'expired': expired,
        'expiringSoon': expiring,
        'expiredCount': len(expired),
        'expiringSoonCount': len(expiring),
        'totalAtRisk': len(expired) + len(expiring),
        'potentialWasteValue': round(sum(i.get('price',0)*i.get('quantity',1) for i in expired), 2)
    })

# ─── Shopping List ──────────────────────────────────────────
@app.route('/api/shopping', methods=['GET'])
@handle_db_error
def get_shopping():
    if DB_AVAILABLE:
        items = [i.to_dict() for i in ShoppingItem.query.filter_by(user_id='default').all()]
    else:
        items = load_file_data().get('shopping', [])
    total = sum(i.get('estimatedPrice',0)*i.get('quantity',1) for i in items)
    return jsonify({'items': items, 'count': len(items), 'estimatedTotal': round(total,2)})

@app.route('/api/shopping', methods=['POST'])
@handle_db_error
def add_shopping_item():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 422

    if DB_AVAILABLE:
        item = ShoppingItem(name=name[:200], category=data.get('category','Other'),
                            quantity=int(data.get('quantity',1)),
                            unit=data.get('unit',''), estimated_price=float(data.get('estimatedPrice',0)),
                            priority=data.get('priority','medium'))
        db.session.add(item); db.session.commit()
        return jsonify(item.to_dict()), 201
    else:
        file_data = load_file_data()
        item = {'id':uuid.uuid4().hex,'name':name,'category':data.get('category','Other'),
                'quantity':int(data.get('quantity',1)),'unit':data.get('unit',''),
                'estimatedPrice':float(data.get('estimatedPrice',0)),'priority':data.get('priority','medium'),
                'checked':False,'addedAt':datetime.utcnow().isoformat()}
        file_data.setdefault('shopping',[]).append(item)
        save_file_data(file_data)
        return jsonify(item), 201

@app.route('/api/shopping/<item_id>', methods=['DELETE'])
@handle_db_error
def delete_shopping_item(item_id):
    if DB_AVAILABLE:
        item = ShoppingItem.query.get_or_404(item_id)
        db.session.delete(item); db.session.commit()
    else:
        file_data = load_file_data()
        file_data['shopping'] = [i for i in file_data.get('shopping',[]) if i['id'] != item_id]
        save_file_data(file_data)
    return jsonify({'success': True})

@app.route('/api/shopping/<item_id>/toggle', methods=['POST'])
@handle_db_error
def toggle_shopping_item(item_id):
    if DB_AVAILABLE:
        item = ShoppingItem.query.get_or_404(item_id)
        item.checked = not item.checked
        db.session.commit()
        return jsonify(item.to_dict())
    else:
        file_data = load_file_data()
        for item in file_data.get('shopping',[]):
            if item['id'] == item_id:
                item['checked'] = not item.get('checked', False)
                save_file_data(file_data)
                return jsonify(item)
        abort(404)

@app.route('/api/shopping/auto-generate', methods=['POST'])
@handle_db_error
def auto_generate_shopping():
    """Auto-generate shopping list from expired/expiring items."""
    today = date.today()
    warn_date = (today + timedelta(days=2)).isoformat()
    today_str = today.isoformat()

    if DB_AVAILABLE:
        items = [i.to_dict() for i in GroceryItem.query.filter_by(user_id='default').all()]
        existing = {i.name.lower() for i in ShoppingItem.query.filter_by(user_id='default').all()}
    else:
        data = load_file_data()
        items = data.get('items', [])
        existing = {i['name'].lower() for i in data.get('shopping', [])}

    to_add = []
    for item in items:
        if item['name'].lower() in existing:
            continue
        exp = item.get('expiryDate')
        priority = None
        if exp and exp < today_str:
            priority = 'high'
        elif exp and exp <= warn_date:
            priority = 'medium'
        if priority:
            to_add.append({
                'id': uuid.uuid4().hex, 'name': item['name'], 'category': item.get('category','Other'),
                'quantity': 1, 'unit': item.get('unit','units'),
                'estimatedPrice': item.get('price',0), 'priority': priority,
                'checked': False, 'addedAt': datetime.utcnow().isoformat()
            })

    if to_add:
        if DB_AVAILABLE:
            for it in to_add:
                db.session.add(ShoppingItem(id=it['id'],name=it['name'],category=it['category'],
                                           estimated_price=it['estimatedPrice'],priority=it['priority']))
            db.session.commit()
        else:
            file_data = load_file_data()
            file_data.setdefault('shopping',[]).extend(to_add)
            save_file_data(file_data)

    return jsonify({'added': len(to_add), 'items': to_add})

# ─── Analytics ──────────────────────────────────────────────
@app.route('/api/analytics')
@handle_db_error
def get_analytics():
    date_from = request.args.get('from', (date.today() - timedelta(days=30)).isoformat())
    date_to = request.args.get('to', date.today().isoformat())

    if DB_AVAILABLE:
        items = [i.to_dict() for i in GroceryItem.query.filter_by(user_id='default').all()]
    else:
        items = load_file_data().get('items', [])

    # Filter by date range
    period_items = [i for i in items if date_from <= (i.get('purchaseDate') or '') <= date_to]
    total_spend = sum(i.get('price',0)*i.get('quantity',1) for i in period_items)

    # Category breakdown
    cat_map = {}
    for item in period_items:
        cat = item.get('category','Other')
        cat_map[cat] = cat_map.get(cat, 0) + item.get('price',0)*item.get('quantity',1)

    # Daily spending
    daily = {}
    for item in period_items:
        d = item.get('purchaseDate','')
        if d:
            daily[d] = daily.get(d,0) + item.get('price',0)*item.get('quantity',1)

    today_str = date.today().isoformat()
    expired_items = [i for i in items if i.get('expiryDate') and i['expiryDate'] < today_str]
    waste_value = sum(i.get('price',0)*i.get('quantity',1) for i in expired_items)

    return jsonify({
        'period': {'from': date_from, 'to': date_to},
        'totalSpend': round(total_spend, 2),
        'itemCount': len(period_items),
        'avgPerItem': round(total_spend / len(period_items), 2) if period_items else 0,
        'categoryBreakdown': {k: round(v, 2) for k,v in sorted(cat_map.items(), key=lambda x: -x[1])},
        'dailySpending': {k: round(v, 2) for k,v in sorted(daily.items())},
        'wasteValue': round(waste_value, 2),
        'expiredCount': len(expired_items),
    })

# ─── OCR Endpoint ───────────────────────────────────────────
@app.route('/api/ocr', methods=['POST'])
def ocr_receipt():
    """Server-side OCR using pytesseract."""
    if not OCR_AVAILABLE:
        return jsonify({'error': 'OCR not available', 'message': 'Install pytesseract and Pillow'}), 503

    if 'image' not in request.files:
        return jsonify({'error': 'No image file provided'}), 400

    file = request.files['image']
    if not file or not file.filename:
        return jsonify({'error': 'Empty file'}), 400

    allowed = {'image/jpeg','image/png','image/gif','image/bmp','image/tiff','image/webp'}
    if file.content_type not in allowed:
        return jsonify({'error': 'Unsupported file type', 'allowed': list(allowed)}), 415

    try:
        img_bytes = file.read()
        if len(img_bytes) > 10 * 1024 * 1024:
            return jsonify({'error': 'File too large', 'maxSizeMB': 10}), 413

        image = Image.open(io.BytesIO(img_bytes))

        # Enhance image for better OCR
        image = image.convert('L')  # Grayscale
        image = image.point(lambda x: 0 if x < 128 else 255, '1')  # Binarize

        raw_text = pytesseract.image_to_string(image, config='--psm 6')
        lines = [l.strip() for l in raw_text.split('\n') if l.strip()]

        # Parse receipt items
        items = parse_receipt_lines(lines)
        logger.info(f"OCR processed: {len(lines)} lines, {len(items)} items detected")

        return jsonify({
            'rawText': raw_text,
            'lines': lines,
            'items': items,
            'itemCount': len(items)
        })

    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract binary not found")
        return jsonify({'error': 'Tesseract not installed', 'message': 'Install Tesseract OCR binary from https://github.com/tesseract-ocr/tesseract'}), 503
    except Exception as e:
        logger.error(f"OCR error: {e}", exc_info=True)
        return jsonify({'error': 'OCR processing failed', 'message': str(e)}), 500

def parse_receipt_lines(lines):
    """Parse receipt text lines into structured items."""
    import re
    items = []
    price_pattern = re.compile(r'\$?(\d+\.\d{2})')
    skip_pattern = re.compile(
        r'^(subtotal|total|tax|change|cash|credit|visa|mastercard|thank|receipt|'
        r'store|date|time|tel|phone|address|welcome|\d{10,})',
        re.IGNORECASE
    )
    for line in lines:
        if skip_pattern.match(line.strip()):
            continue
        price_match = price_pattern.search(line)
        price = float(price_match.group(1)) if price_match else None
        name = price_pattern.sub('', line).strip()
        name = re.sub(r'^\d+\s+x?\s*', '', name, flags=re.IGNORECASE).strip()
        name = re.sub(r'\s+', ' ', name).strip()
        if len(name) > 1 and len(name) < 60:
            items.append({'name': name[:50], 'price': price, 'quantity': 1})
    return items[:20]

# ─── Export / Import ────────────────────────────────────────
@app.route('/api/export')
@handle_db_error
def export_data():
    if DB_AVAILABLE:
        items = [i.to_dict() for i in GroceryItem.query.filter_by(user_id='default').all()]
        shopping = [i.to_dict() for i in ShoppingItem.query.filter_by(user_id='default').all()]
    else:
        data = load_file_data()
        items = data.get('items', [])
        shopping = data.get('shopping', [])

    export = {
        'version': '2.0.0',
        'exportedAt': datetime.utcnow().isoformat(),
        'items': items,
        'shopping': shopping,
    }
    from flask import Response
    return Response(
        json.dumps(export, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename=pantryos-export-{date.today()}.json'}
    )

@app.route('/api/import', methods=['POST'])
@handle_db_error
def import_data():
    if not request.is_json:
        return jsonify({'error': 'Content-Type must be application/json'}), 400

    data = request.get_json()
    if not data or 'items' not in data:
        return jsonify({'error': 'Invalid export format'}), 422

    items = data.get('items', [])
    shopping = data.get('shopping', [])

    # Validate items
    valid_items = []
    skipped = 0
    for item in items:
        is_valid, _ = validate_item_data(item)
        if is_valid:
            valid_items.append(item)
        else:
            skipped += 1

    if DB_AVAILABLE:
        GroceryItem.query.filter_by(user_id='default').delete()
        ShoppingItem.query.filter_by(user_id='default').delete()
        for item in valid_items:
            db.session.add(GroceryItem(
                id=item.get('id', uuid.uuid4().hex), name=item['name'],
                category=item.get('category','Other'), price=float(item.get('price',0)),
                quantity=float(item.get('quantity',1)), unit=item.get('unit','units'),
                purchase_date=item.get('purchaseDate'), expiry_date=item.get('expiryDate'),
            ))
        db.session.commit()
    else:
        save_file_data({'items': valid_items, 'shopping': shopping})

    logger.info(f"Import: {len(valid_items)} items, {skipped} skipped")
    return jsonify({'imported': len(valid_items), 'skipped': skipped})

# ─── Static Files ───────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    safe_name = os.path.basename(filename)
    allowed_ext = {'.html','.js','.css','.json','.png','.svg','.ico','.webp'}
    if os.path.splitext(safe_name)[1] not in allowed_ext:
        abort(403)
    return send_from_directory('.', filename)

# ─── Init & Run ─────────────────────────────────────────────
if __name__ == '__main__':
    if DB_AVAILABLE:
        with app.app_context():
            db.create_all()
            logger.info("Database tables created/verified")

    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'true').lower() == 'true'

    logger.info(f"Starting PantryOS on port {port}")
    logger.info(f"OCR available: {OCR_AVAILABLE}")
    logger.info(f"SQLAlchemy available: {DB_AVAILABLE}")
    logger.info(f"Visit: http://localhost:{port}")

    app.run(host='0.0.0.0', port=port, debug=debug)
