import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import math

app = Flask(__name__)
app.config['SECRET_KEY'] = 'blood_exchange_secret_key_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Database Models ---

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

# --- Helper Functions ---

def calculate_distance(lat1, lon1, lat2, lon2):
    # Haversine formula
    R = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

# Mock Geocoding (Assigns random coords based on name length for demo purposes)
def get_coords(address):
    return (40.7128 + (len(address) % 10) * 0.01, -74.0060 + (len(address) % 10) * 0.01)

# --- Routes ---

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        address = request.form['address']
        lat, lng = get_coords(address)

        if Hospital.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('signup'))

        new_hosp = Hospital(name=name, email=email, password=password, address=address, lat=lat, lng=lng)
        db.session.add(new_hosp)
        db.session.commit()
        return redirect(url_for('index'))
    return render_template('signup.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    hospital = Hospital.query.filter_by(email=email).first()

    if hospital and check_password_hash(hospital.password, password):
        session['hospital_id'] = hospital.id
        return redirect(url_for('dashboard'))
    flash('Invalid credentials')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'hospital_id' not in session: return redirect(url_for('index'))
    hosp = Hospital.query.get(session['hospital_id'])
    # Logic: Only show blood updated within last 42 days
    expiry_limit = datetime.utcnow() - timedelta(days=42)
    inventory = BloodInventory.query.filter_by(hospital_id=hosp.id).all()
    return render_template('dashboard.html', hospital=hosp, inventory=inventory, limit=expiry_limit)

@app.route('/update_blood', methods=['POST'])
def update_blood():
    if 'hospital_id' not in session: return redirect(url_for('index'))
    bg = request.form['blood_group']
    qty = int(request.form['quantity'])
    
    entry = BloodInventory.query.filter_by(hospital_id=session['hospital_id'], blood_group=bg).first()
    if entry:
        entry.quantity = qty
        entry.last_updated = datetime.utcnow()
    else:
        new_entry = BloodInventory(hospital_id=session['hospital_id'], blood_group=bg, quantity=qty)
        db.session.add(new_entry)
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/search', methods=['GET', 'POST'])
def search():
    results = []
    if request.method == 'POST':
        bg = request.form['blood_group']
        current_hosp = Hospital.query.get(session.get('hospital_id'))
        expiry_limit = datetime.utcnow() - timedelta(days=42)

        # Filter: Right blood group, quantity > 0, and not expired
        matches = BloodInventory.query.filter(
            BloodInventory.blood_group == bg,
            BloodInventory.quantity > 0,
            BloodInventory.last_updated > expiry_limit
        ).all()

        for match in matches:
            dist = 0
            if current_hosp:
                dist = calculate_distance(current_hosp.lat, current_hosp.lng, match.owner.lat, match.owner.lng)
            results.append({'hospital': match.owner, 'qty': match.quantity, 'dist': round(dist, 2)})
        
        results.sort(key=lambda x: x['dist'])

    return render_template('search.html', results=results)

@app.route('/logout')
def logout():
    session.pop('hospital_id', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
