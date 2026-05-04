import os
import math
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- CONFIGURATION ---
# Use an absolute path for SQLite to avoid 'no such table' errors on Render
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'blood-exchange-secret-123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELS ---
class Hospital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(200), nullable=False)
    lat = db.Column(db.Float)
    lng = db.Column(db.Float)
    inventory = db.relationship('BloodInventory', backref='owner', lazy=True)

class BloodInventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'), nullable=False)
    blood_group = db.Column(db.String(5), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

# --- DB INITIALIZATION ---
# This ensures the database file and tables are created immediately when Render starts the app
with app.app_context():
    db.create_all()

# --- HELPERS ---
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))

def get_coords(address):
    return (40.7128 + (len(address) % 10) * 0.01, -74.0060 + (len(address) % 10) * 0.01)

# --- ROUTES ---
@app.route('/', methods=['GET', 'HEAD'])
def index():
    if request.method == 'HEAD':
        return '', 200
    if 'hospital_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name, email, addr = request.form['name'], request.form['email'], request.form['address']
        pwd = generate_password_hash(request.form['password'])
        if Hospital.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('signup'))
        lat, lng = get_coords(addr)
        new_h = Hospital(name=name, email=email, password=pwd, address=addr, lat=lat, lng=lng)
        db.session.add(new_h)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('signup.html')

@app.route('/login', methods=['POST'])
def login():
    h = Hospital.query.filter_by(email=request.form['email']).first()
    if h and check_password_hash(h.password, request.form['password']):
        session['hospital_id'] = h.id
        return redirect(url_for('dashboard'))
    flash('Invalid Email or Password')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'hospital_id' not in session: return redirect(url_for('index'))
    h = Hospital.query.get(session['hospital_id'])
    limit = datetime.utcnow() - timedelta(days=42)
    return render_template('dashboard.html', hospital=h, inventory=h.inventory, limit=limit)

@app.route('/update_blood', methods=['POST'])
def update_blood():
    if 'hospital_id' not in session: return redirect(url_for('index'))
    bg, qty = request.form['blood_group'], int(request.form['quantity'])
    entry = BloodInventory.query.filter_by(hospital_id=session['hospital_id'], blood_group=bg).first()
    if entry:
        entry.quantity, entry.last_updated = qty, datetime.utcnow()
    else:
        db.session.add(BloodInventory(hospital_id=session['hospital_id'], blood_group=bg, quantity=qty))
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/search', methods=['GET', 'POST'])
def search():
    results = []
    if request.method == 'POST':
        bg = request.form['blood_group']
        limit = datetime.utcnow() - timedelta(days=42)
        curr = Hospital.query.get(session.get('hospital_id'))
        matches = BloodInventory.query.filter(BloodInventory.blood_group == bg, 
                                            BloodInventory.quantity > 0, 
                                            BloodInventory.last_updated > limit).all()
        for m in matches:
            d = calculate_distance(curr.lat, curr.lng, m.owner.lat, m.owner.lng) if curr else 0
            results.append({'hospital': m.owner, 'qty': m.quantity, 'dist': round(d, 2)})
        results.sort(key=lambda x: x['dist'])
    return render_template('search.html', results=results)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
