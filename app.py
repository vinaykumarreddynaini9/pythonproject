from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, login_required,
    logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import or_, and_
from flask_mail import Mail, Message
import random
import os

# -----------------
# App & DB setup
# -----------------
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# SQL Server (Azure) connection
app.config['SQLALCHEMY_DATABASE_URI'] = 'mssql+pyodbc://adminuser:Vinay14061995@coriderserver.database.windows.net/coriderdb?driver=ODBC+Driver+18+for+SQL+Server'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -----------------
# Login
# -----------------
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# -----------------
# Email (Flask-Mail)
# -----------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'vinaykumarreddynaini9@gmail.com'
app.config['MAIL_PASSWORD'] = 'vttb oeqz fyvu puob'  # Gmail App Password
app.config['MAIL_DEFAULT_SENDER'] = ('CO-RIDER', app.config['MAIL_USERNAME'])

mail = Mail(app)

def safe_email(to, subject, body):
    try:
        if not to:
            return
        msg = Message(subject=subject, recipients=[to], body=body)
        mail.send(msg)
    except Exception as e:
        pass

# -----------------
# Models
# -----------------
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    phone = db.Column(db.String(20), nullable=False)
    password = db.Column(db.String(256), nullable=False)

    # Relationships
    bookings = db.relationship("Booking", back_populates="user", cascade="all, delete-orphan")
    rides = db.relationship("Ride", back_populates="driver", cascade="all, delete-orphan")


class Ride(db.Model):
    __tablename__ = 'rides'
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    driver_username = db.Column(db.String(150), nullable=False)
    driver_phone = db.Column(db.String(20), nullable=False)
    vehicle_number = db.Column(db.String(50), nullable=False)
    vehicle_model = db.Column(db.String(100), nullable=False)
    from_city = db.Column(db.String(100), nullable=False)
    to_city = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    seats_available = db.Column(db.Integer, nullable=False)
    fare_per_seat = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="Scheduled")  # Scheduled, Started, Ended

    # Relationships
    bookings = db.relationship("Booking", back_populates="ride", cascade="all, delete-orphan")
    driver = db.relationship("User", back_populates="rides", foreign_keys=[driver_id])
    ratings = db.relationship("Rating", back_populates="ride", cascade="all, delete-orphan")


class Booking(db.Model):
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    ride_id = db.Column(db.Integer, db.ForeignKey('rides.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    seats_booked = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending, approved, rejected

    # Relationships
    ride = db.relationship("Ride", back_populates="bookings")
    user = db.relationship("User", back_populates="bookings")


class Rating(db.Model):
    __tablename__ = 'ratings'
    id = db.Column(db.Integer, primary_key=True)
    ride_id = db.Column(db.Integer, db.ForeignKey('rides.id'), nullable=False)
    passenger_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(255))

    # Relationships
    ride = db.relationship("Ride", back_populates="ratings")
    passenger = db.relationship("User")

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -----------------
# Helpers
# -----------------
ALLOWED_CITIES = ['Siddipet','Hyderabad','Nizambad','Karimnagar','warangal','medak','uppal','kompally']

def is_upcoming(ride: Ride) -> bool:
    now = datetime.now()
    ride_dt = datetime.combine(ride.date, ride.time)
    return ride_dt >= now

def upcoming_filter():
    now = datetime.now()
    today = now.date()
    now_time = now.time()
    five_minutes_earlier = (datetime.combine(today, now_time) + timedelta(minutes=5)).time()
    return or_(
        Ride.date > today,
        and_(Ride.date == today, Ride.time >= five_minutes_earlier)
    )

def passenger_has_upcoming_booking(user_id: int) -> bool:
    now = datetime.now()
    today, now_time = now.date(), now.time()
    return db.session.query(Booking).join(Ride, Booking.ride_id == Ride.id).filter(
        Booking.user_id == user_id,
        or_(Ride.date > today, and_(Ride.date == today, Ride.time >= now_time))
    ).first() is not None

def driver_has_upcoming_ride(user_id: int) -> bool:
    return Ride.query.filter(Ride.driver_id == user_id, upcoming_filter()).first() is not None

def generate_otp():
    return str(random.randint(100000, 999999))

# -----------------
# Routes
# -----------------
@app.route('/')
def index():
    return redirect(url_for('signup'))

# ---- Signup with OTP ----
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip().lower()
        phone = request.form['phone'].strip()
        password_raw = request.form['password']

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already exists!', 'danger')
            return redirect(url_for('signup'))

        # Generate OTP and store temporarily in session
        otp = generate_otp()
        session['pending_user'] = {
            'username': username,
            'email': email,
            'phone': phone,
            'password': generate_password_hash(password_raw, method='pbkdf2:sha256')
        }
        session['otp'] = otp
        safe_email(email, "CO-RIDER Signup OTP", f"Your OTP is {otp}. It is valid for 5 minutes.")
        flash("OTP sent to your email. Please verify.", "info")
        return redirect(url_for('verify_signup_otp'))
    return render_template('signup.html')

@app.route('/verify_signup_otp', methods=['GET','POST'])
def verify_signup_otp():
    if request.method == 'POST':
        otp_entered = request.form['otp']
        if otp_entered == session.get('otp'):
            data = session.pop('pending_user', None)
            if data:
                new_user = User(**data)
                db.session.add(new_user)
                db.session.commit()
                flash("Signup successful! Please login.", "success")
                return redirect(url_for('login'))
        flash("Invalid OTP. Please try again.", "danger")
    return render_template('verify_otp.html')

# ---- Login ----
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        flash('Invalid credentials', 'danger')
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/home')
@login_required
def home():
    return render_template('home.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ---- Profile with OTP for changes ----
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = current_user
    if request.method == 'POST':
        # Start OTP process before saving
        otp = generate_otp()
        session['profile_update'] = {
            'email': request.form['email'].strip().lower(),
            'phone': request.form['phone'].strip(),
            'password': request.form.get('password')
        }
        session['otp'] = otp
        safe_email(user.email, "CO-RIDER Profile Update OTP", f"Your OTP is {otp}.")
        flash("OTP sent to your email. Please verify to apply changes.", "info")
        return redirect(url_for('verify_profile_otp'))
    return render_template('profile.html', user=user)

@app.route('/verify_profile_otp', methods=['GET','POST'])
@login_required
def verify_profile_otp():
    if request.method == 'POST':
        otp_entered = request.form['otp']
        if otp_entered == session.get('otp'):
            data = session.pop('profile_update', None)
            if data:
                current_user.email = data['email']
                current_user.phone = data['phone']
                if data['password']:
                    current_user.password = generate_password_hash(data['password'], method='pbkdf2:sha256')
                db.session.commit()
                flash("Profile updated successfully!", "success")
                return redirect(url_for('profile'))
        flash("Invalid OTP.", "danger")
    return render_template('verify_otp.html')

# ---- Post Ride (driver-only if no upcoming passenger booking) ----
@app.route('/post_ride', methods=['GET', 'POST'])
@login_required
def post_ride():
    # Prevent posting while having a booking as passenger
    existing_booking = Booking.query.filter_by(user_id=current_user.id).first()
    if existing_booking:
        flash("You cannot post a ride while you have booked a ride as a passenger.", "danger")
        return redirect(url_for('find_rides'))

    # ✅ Prevent posting more than 3 active rides
    active_rides = Ride.query.filter(
        Ride.driver_id == current_user.id,
        Ride.status == "Scheduled"   # or "Upcoming" depending on your model
    ).count()
    if active_rides >= 3:
        flash("❌ You cannot post more than 3 active rides at a time.", "danger")
        return redirect(url_for('my_rides'))

    if request.method == 'POST':
        from_city = request.form.get('from_city')
        to_city = request.form.get('to_city')
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        seats = request.form.get('seats')
        fare_per_seat = request.form.get('fare_per_seat')
        driver_phone = request.form.get('driver_phone')
        vehicle_number = request.form.get('vehicle_number')
        vehicle_model = request.form.get('vehicle_model')

        # Basic validations
        if not all([from_city, to_city, date_str, time_str, seats, fare_per_seat, driver_phone, vehicle_number, vehicle_model]):
            flash("Please fill in all fields.", "danger")
            return redirect(url_for('post_ride'))

        seats = int(seats)
        fare_per_seat = int(fare_per_seat)

        # Fare validation
        if fare_per_seat < 180 or fare_per_seat > 400:
            flash("Fare must be between ₹180 and ₹400.", "danger")
            return redirect(url_for('post_ride'))

        # Parse date/time
        ride_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        ride_time = datetime.strptime(time_str, "%H:%M").time()
        ride_datetime = datetime.combine(ride_date, ride_time)
        now = datetime.now()

        # Only today or tomorrow allowed
        if ride_date < now.date() or ride_date > (now.date() + timedelta(days=1)):
            flash("You can only post rides for today or tomorrow.", "danger")
            return redirect(url_for('post_ride'))

        # Cutoff time: 30 minutes before ride
        cutoff = ride_datetime - timedelta(minutes=30)
        if now > cutoff:
            flash(f"You cannot post a ride less than 30 minutes before departure time.", "danger")
            return redirect(url_for('post_ride'))

        # Create new ride
        new_ride = Ride(
            driver_id=current_user.id,
            driver_username=current_user.username,
            from_city=from_city,
            to_city=to_city,
            date=ride_date,
            time=ride_time,
            seats_available=seats,
            fare_per_seat=fare_per_seat,
            driver_phone=driver_phone,
            vehicle_number=vehicle_number,
            vehicle_model=vehicle_model,
            status="Scheduled"
        )
        db.session.add(new_ride)
        db.session.commit()
        flash("✅ Ride posted successfully!", "success")
        return redirect(url_for('find_rides'))

    return render_template('post_ride.html', allowed_cities=ALLOWED_CITIES)


#Start and end ride

from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.start()

def auto_end_ride(ride_id):
    ride = Ride.query.get(ride_id)
    if ride and ride.status == "Started":
        ride.status = "Ended"
        db.session.commit()

@app.route('/start_ride/<int:ride_id>', methods=['POST'])
@login_required
def start_ride(ride_id):
    ride = Ride.query.get_or_404(ride_id)
    if ride.driver_id != current_user.id:
        flash("You cannot start this ride.", "danger")
        return redirect(url_for('my_rides'))

    ride.status = "Started"
    db.session.commit()

    # Schedule auto-end after 5 hours
    scheduler.add_job(auto_end_ride, 'date', run_date=datetime.now() + timedelta(hours=5), args=[ride.id])

    flash("Ride has been started!", "success")
    return redirect(url_for('ride_details', ride_id=ride.id))


@app.route('/end_ride/<int:ride_id>', methods=['POST'])
@login_required
def end_ride(ride_id):
    ride = Ride.query.get_or_404(ride_id)
    if ride.driver_id != current_user.id:
        flash("You cannot end this ride.", "danger")
        return redirect(url_for('my_rides'))

    ride.status = "Ended"
    db.session.commit()

    flash("Ride has been ended!", "success")
    return redirect(url_for('ride_details', ride_id=ride.id))

# ---- Find Rides page (split: my rides vs others; only upcoming) ----
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

@app.route('/find_rides')
@login_required
def find_rides():
    tz = ZoneInfo("Asia/Kolkata")
    now_local = datetime.now(tz)
    cutoff_dt = now_local + timedelta(minutes=10)
    cutoff_date = cutoff_dt.date()
    cutoff_time = cutoff_dt.time()

    # My rides (upcoming)
    my_rides = (
        Ride.query.options(joinedload(Ride.bookings))
        .filter(
            Ride.driver_id == current_user.id,
            or_(
                Ride.date > cutoff_date,
                and_(Ride.date == cutoff_date, Ride.time > cutoff_time)
            )
        )
        .order_by(Ride.date.asc(), Ride.time.asc())
        .all()
    )

    # Other users' rides (upcoming)
    other_rides = (
        Ride.query.options(joinedload(Ride.bookings))
        .filter(
            Ride.driver_id != current_user.id,
            or_(
                Ride.date > cutoff_date,
                and_(Ride.date == cutoff_date, Ride.time > cutoff_time)
            )
        )
        .order_by(Ride.date.asc(), Ride.time.asc())
        .all()
    )

    # Mark them as upcoming (still useful for template)
    for r in my_rides + other_rides:
        r.is_upcoming = True

    return render_template(
        'find_rides.html',
        my_rides=my_rides,
        other_rides=other_rides,
        allowed_cities=ALLOWED_CITIES
    )

# ---- Ride Details page ----
@app.route('/ride/<int:ride_id>')
@login_required
def ride_details(ride_id):
    ride = Ride.query.get_or_404(ride_id)

    # can the current user book this ride?
    reason = None
    can_book = True

    if ride.driver_id == current_user.id:
        can_book = False
        reason = "You cannot book your own ride."

    elif not is_upcoming(ride):
        can_book = False
        reason = "This ride has already departed."

    elif ride.seats_available < 1:
        can_book = False
        reason = "No seats available."

    elif driver_has_upcoming_ride(current_user.id):
        can_book = False
        reason = "You have an upcoming posted ride. Cancel it to book as a passenger."

    elif passenger_has_upcoming_booking(current_user.id):
        # If they already booked *this* ride, say that specifically
        already = Booking.query.filter_by(ride_id=ride.id, user_id=current_user.id).first()
        if already:
            can_book = False
            reason = "You already booked this ride."
        else:
            can_book = False
            reason = "You have an upcoming booking. Cancel it to post/book another ride."

    # ---- Show driver phone only within 30 mins of ride ----
    from datetime import datetime, timedelta

    ride_datetime = datetime.combine(ride.date, ride.time)
    show_driver_phone = False
    if datetime.now() >= ride_datetime - timedelta(minutes=30):
        show_driver_phone = True

    return render_template(
        'ride_details.html',
        ride=ride,
        can_book=can_book,
        reason=reason,
        show_driver_phone=show_driver_phone
    )

#booking

def seats_available(ride):
    """Return remaining seats on this ride considering approved bookings."""
    booked_seats = db.session.query(db.func.coalesce(db.func.sum(Booking.seats_booked), 0)) \
                    .filter_by(ride_id=ride.id, status='approved').scalar()
    return ride.seats_available - booked_seats

@app.route('/book_ride/<int:ride_id>', methods=['POST'])
@login_required
def book_ride(ride_id):
    ride = Ride.query.get_or_404(ride_id)

    if ride.driver_id == current_user.id:
        flash("You cannot book your own ride.", "danger")
        return redirect(url_for('find_rides'))

    available = seats_available(ride)
    if available < 1:
        flash("No seats available for this ride.", "danger")
        return redirect(url_for('find_rides'))

    try:
        seats_to_book = int(request.form.get("seats", 1))
    except ValueError:
        flash("Invalid number of seats.", "danger")
        return redirect(url_for('ride_details', ride_id=ride.id))

    if seats_to_book < 1 or seats_to_book > available:
        flash(f"You can only request 1 to {available} seats.", "danger")
        return redirect(url_for('ride_details', ride_id=ride.id))

    # Create booking
    booking = Booking(
        ride_id=ride.id,
        user_id=current_user.id,
        seats_booked=seats_to_book,
        status="pending"
    )
    db.session.add(booking)
    db.session.commit()

    flash(f"Booking request sent for {seats_to_book} seat(s). Waiting for driver approval.", "success")

    # Optional: email notifications
    if ride.driver and ride.driver.email:
        safe_email(
            to=ride.driver.email,
            subject="New Booking on Your Ride",
            body=f"Hi {ride.driver_username},\n\n{current_user.username} booked {seats_to_book} seat(s) on your ride "
                 f"{ride.from_city} → {ride.to_city} on {ride.date} at {ride.time}.\n\n— CO-RIDER"
        )
    safe_email(
        to=current_user.email,
        subject="Ride Booking Requested",
        body=f"Hi {current_user.username},\n\nYour booking is requested for {ride.from_city} → {ride.to_city} "
             f"on {ride.date} at {ride.time}. Seats: {seats_to_book}.\nDriver: {ride.driver_username}.\n\n— CO-RIDER"
    )

    return redirect(url_for('my_trips'))

# Approve Booking Route
@app.route('/approve_booking/<int:booking_id>', methods=['POST'])
@login_required
def approve_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    ride = booking.ride

    if ride.driver_id != current_user.id:
        flash("Not authorized.", "danger")
        return redirect(url_for('my_rides'))

    if booking.status != "pending":
        flash("This booking is already processed.", "info")
        return redirect(url_for('ride_passengers', ride_id=ride.id))

    available_seats = ride.seats_available
    if booking.seats_booked > available_seats:
        booking.status = "rejected"
        flash("Not enough seats left. Booking rejected automatically.", "danger")

        # Send rejection email
        send_email(
            booking.user.email,
            "Booking Rejected",
            f"Dear {booking.user.username},\n\n"
            f"Your booking for the ride {ride.from_city} → {ride.to_city} on {ride.date} "
            f"at {ride.time} was rejected due to insufficient seats.\n\nRegards,\nCO-RIDER"
        )
    else:
        booking.status = "approved"
        ride.seats_available = available_seats - booking.seats_booked
        flash(f"Booking approved for {booking.user.username}.", "success")

        # Send approval email
        send_email(
            booking.user.email,
            "Booking Approved",
            f"Dear {booking.user.username},\n\n"
            f"Your booking for {booking.seats_booked} seat(s) on the ride "
            f"{ride.from_city} → {ride.to_city} on {ride.date} at {ride.time} "
            f"has been approved.\n\nHappy riding!\nCO-RIDER"
        )

    db.session.commit()
    return redirect(url_for('ride_passengers', ride_id=ride.id))


# Reject Booking Route
@app.route('/reject_booking/<int:booking_id>', methods=['POST'])
@login_required
def reject_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    ride = booking.ride

    if ride.driver_id != current_user.id:
        flash("Not authorized.", "danger")
        return redirect(url_for('my_rides'))

    if booking.status == "pending":
        booking.status = "rejected"
        flash(f"Booking rejected for {booking.user.username}.", "warning")

        # Send rejection email
        send_email(
            booking.user.email,
            "Booking Rejected",
            f"Dear {booking.user.username},\n\n"
            f"Your booking for the ride {ride.from_city} → {ride.to_city} on {ride.date} "
            f"at {ride.time} was rejected by the driver.\n\nRegards,\nCO-RIDER"
        )

    elif booking.status == "approved":
        # Restore seats
        ride.seats_available += booking.seats_booked
        booking.status = "rejected"
        flash(f"Booking rejected and {booking.seats_booked} seat(s) restored for {booking.user.username}.", "warning")

        # Send rejection email
        send_email(
            booking.user.email,
            "Booking Rejected",
            f"Dear {booking.user.username},\n\n"
            f"Your approved booking for {booking.seats_booked} seat(s) on the ride "
            f"{ride.from_city} → {ride.to_city} on {ride.date} at {ride.time} "
            f"was rejected by the driver. The seats have been restored to availability.\n\nRegards,\nCO-RIDER"
        )
    else:
        flash("Booking already processed.", "info")

    db.session.commit()
    return redirect(url_for('ride_passengers', ride_id=ride.id))

# ---- Config: platform fee (in %) ----
PLATFORM_FEE_PERCENT = 10  # change anytime

# ---- My Earnings (Driver) ----
@app.route('/my_earnings')
@login_required
def my_earnings():
    # All rides posted by this user
    rides = (
        Ride.query
        .filter_by(driver_id=current_user.id)
        .order_by(Ride.date.asc(), Ride.time.asc())
        .all()
    )

    rows = []
    total_fare_sum = 0
    platform_fee_sum = 0
    driver_earnings_sum = 0

    for r in rides:
        # Only approved bookings count toward earnings
        approved_bookings = [b for b in r.bookings if b.status == "approved"]
        seats_approved = sum(b.seats_booked for b in approved_bookings)

        if seats_approved == 0:
            continue  # skip rides with no approved seats

        fare_per_seat = r.fare_per_seat or 0
        total_fare = seats_approved * fare_per_seat
        platform_fee = (total_fare * PLATFORM_FEE_PERCENT) // 100
        driver_earning = total_fare - platform_fee

        total_fare_sum += total_fare
        platform_fee_sum += platform_fee
        driver_earnings_sum += driver_earning

        rows.append({
            "ride": r,
            "date": r.date,
            "time": r.time,
            "route": f"{r.from_city} → {r.to_city}",
            "seats": seats_approved,
            "fare_per_seat": fare_per_seat,
            "total_fare": total_fare,
            "platform_fee": platform_fee,
            "driver_earning": driver_earning,
            "status": r.status  # Scheduled / Started / Ended
        })

    return render_template(
        'my_earnings.html',
        rows=rows,
        platform_fee_percent=PLATFORM_FEE_PERCENT,
        total_fare_sum=total_fare_sum,
        platform_fee_sum=platform_fee_sum,
        driver_earnings_sum=driver_earnings_sum
    )

#My trips   
@app.route('/my_trips')
@login_required
def my_trips():
    my_bookings = (
        Booking.query.filter_by(user_id=current_user.id)
        .join(Ride, Booking.ride_id == Ride.id)
        .order_by(Ride.date, Ride.time)
        .all()
    )

    upcoming_bookings = [
        b for b in my_bookings
        if b.ride.status in ["Scheduled", "Started"] and is_upcoming(b.ride)
    ]
    past_bookings = [
        b for b in my_bookings
        if b.ride.status == "Ended" or not is_upcoming(b.ride)
    ]

    return render_template(
        'my_trips.html',
        upcoming_bookings=upcoming_bookings,
        past_bookings=past_bookings
    )

# ---- My Rides (Driver) split into upcoming/past + cancel) ----
from sqlalchemy.sql import func

@app.route('/my_rides')
@login_required
def my_rides():
    rides = Ride.query.filter_by(driver_id=current_user.id)\
        .order_by(Ride.date, Ride.time).all()

    upcoming_rides = [r for r in rides if is_upcoming(r)]
    past_rides = [r for r in rides if not is_upcoming(r)]

    # Attach average rating
    for ride in past_rides:
        avg_rating = db.session.query(func.avg(Booking.rating))\
            .filter(Booking.ride_id == ride.id, Booking.rating.isnot(None))\
            .scalar()
        ride.average_rating = round(avg_rating, 1) if avg_rating else None

    return render_template("my_rides.html", upcoming_rides=upcoming_rides, past_rides=past_rides)

#cancel booking
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    if booking.user_id != current_user.id:
        flash("You are not allowed to cancel this booking.", "danger")
        return redirect(url_for('my_trips'))

    ride = booking.ride
    # only allow cancel for upcoming rides
    if not is_upcoming(ride):
        flash("This ride has already departed.", "warning")
        return redirect(url_for('my_trips'))

    # restrict cancellation if ride < 30 minutes away
    tz = ZoneInfo("Asia/Kolkata")
    ride_dt = datetime.combine(ride.date, ride.time, tzinfo=tz)
    now_local = datetime.now(tz)
    if ride_dt - now_local < timedelta(minutes=30):
        flash("❌ You cannot cancel a booking less than 30 minutes before departure.", "danger")
        return redirect(url_for('my_trips'))

    ride.seats_available += booking.seats_booked
    db.session.delete(booking)
    db.session.commit()

    # email notify driver and passenger
    safe_email(
        to=current_user.email,
        subject="Booking Cancelled",
        body=f"Hi {current_user.username},\n\nYour booking for {ride.from_city} → {ride.to_city} on {ride.date} at {ride.time} "
             f"has been cancelled.\n\n— CO-RIDER"
    )
    if ride.driver and ride.driver.email:
        safe_email(
            to=ride.driver.email,
            subject="Booking Cancelled by Passenger",
            body=f"Hi {ride.driver_username},\n\n{current_user.username} cancelled their booking on your ride "
                 f"{ride.from_city} → {ride.to_city} on {ride.date} at {ride.time}.\n\n— CO-RIDER"
        )

    flash("Booking cancelled successfully!", "success")
    return redirect(url_for('my_trips'))

#cancel booking driver
@app.route('/cancel_booking_driver/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking_driver(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    ride = booking.ride

    if ride.driver_id != current_user.id:
        flash("Not authorized.", "danger")
        return redirect(url_for('my_rides'))

    if booking.status != "approved":
        flash("Only approved bookings can be cancelled by driver.", "info")
        return redirect(url_for('ride_passengers', ride_id=ride.id))

    ride.seats_available += booking.seats_booked
    booking.status = "cancelled_by_driver"
    db.session.commit()
    flash(f"Booking for {booking.user.username} cancelled. Seats released.", "warning")
    return redirect(url_for('ride_passengers', ride_id=ride.id))

# ---- Cancel Ride (driver) ----
@app.route('/cancel_ride/<int:ride_id>', methods=['POST'])
@login_required
def cancel_ride(ride_id):
    ride = Ride.query.get_or_404(ride_id)
    if ride.driver_id != current_user.id:
        flash("You are not allowed to cancel this ride.", "danger")
        return redirect(url_for('my_rides'))

    # restrict driver cancellation if ride < 30min AND passengers booked
    tz = ZoneInfo("Asia/Kolkata")
    ride_dt = datetime.combine(ride.date, ride.time, tzinfo=tz)
    now_local = datetime.now(tz)
    if ride_dt - now_local < timedelta(minutes=30) and ride.bookings:
        flash("❌ You cannot cancel this ride within 30 minutes of departure since passengers are booked.", "danger")
        return redirect(url_for('my_rides'))

    # notify passengers
    passenger_emails = [b.user.email for b in ride.bookings if b.user and b.user.email]
    for pe in passenger_emails:
        safe_email(
            to=pe,
            subject="Ride Cancelled",
            body=f"Hello,\n\nThe ride {ride.from_city} → {ride.to_city} on {ride.date} at {ride.time} "
                 f"has been cancelled by the driver {ride.driver_username}.\n\n— CO-RIDER"
        )

    # Delete bookings then ride
    Booking.query.filter_by(ride_id=ride.id).delete()
    db.session.delete(ride)
    db.session.commit()

    flash("Ride cancelled successfully!", "success")
    return redirect(url_for('my_rides'))

@app.route('/ride/<int:ride_id>/passengers')
@login_required
def ride_passengers(ride_id):
    ride = Ride.query.get_or_404(ride_id)

    # Only driver can view passengers of their ride
    if ride.driver_id != current_user.id:
        flash("You are not allowed to view passengers of this ride.", "danger")
        return redirect(url_for('my_rides'))

    bookings = Booking.query.filter_by(ride_id=ride.id).all()
    return render_template('ride_passengers.html', ride=ride, bookings=bookings)   

@app.route('/rate_ride/<int:ride_id>', methods=['POST'])
@login_required
def rate_ride(ride_id):
    ride = Ride.query.get_or_404(ride_id)
    rating_val = int(request.form.get("rating"))
    comment = request.form.get("comment")

    # ✅ allow only after ride date
    if ride.date >= date.today():
        flash("You can only rate after the ride date.", "danger")
        return redirect(url_for('my_trips'))

    # ✅ prevent duplicate rating
    existing = Rating.query.filter_by(ride_id=ride_id, passenger_id=current_user.id).first()
    if existing:
        flash("You already rated this ride.", "warning")
        return redirect(url_for('my_trips'))

    new_rating = Rating(ride_id=ride_id, passenger_id=current_user.id, rating=rating_val, comment=comment)
    db.session.add(new_rating)
    db.session.commit()
    flash("Thanks for rating the ride!", "success")
    return redirect(url_for('my_trips'))

# -----------------
# DB init
# -----------------
with app.app_context():
    db.create_all()


if __name__ == "__main__":
  app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))


