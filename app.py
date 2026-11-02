
import os
from pathlib import Path
from datetime import datetime, date
from io import BytesIO

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file
)

from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from dotenv import load_dotenv

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer
)

from models import db, User, Vehicle, FuelRecord


# ==========================================
# APPLICATION CONFIGURATION
# ==========================================

load_dotenv()

app = Flask(__name__)

Path("instance").mkdir(exist_ok=True)

app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY",
    "development-secret-key-change-before-deployment"
)

database_url = os.getenv(
    "DATABASE_URL",
    "sqlite:///fuel_analysis.db"
)

# PostgreSQL URL configuration
if database_url.startswith("postgres://"):
    database_url = database_url.replace(
        "postgres://",
        "postgresql+psycopg://",
        1
    )
elif database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1
    )

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


# ==========================================
# DATABASE INITIALIZATION
# ==========================================

db.init_app(app)


# ==========================================
# LOGIN MANAGER
# ==========================================

login_manager = LoginManager()

login_manager.init_app(app)

login_manager.login_view = "login"

login_manager.login_message = "Please login to continue."


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ==========================================
# HOME PAGE
# ==========================================

@app.route("/")
def index():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    return render_template("index.html")


# ==========================================
# USER REGISTRATION
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get(
            "username", ""
        ).strip()

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("Please fill all fields.", "danger")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash(
                "Password must contain at least 8 characters.",
                "danger"
            )
            return redirect(url_for("register"))

        existing_user = User.query.filter_by(
            email=email
        ).first()

        if existing_user:
            flash("Email already registered.", "danger")
            return redirect(url_for("register"))

        new_user = User(
            username=username,
            email=email,
            password=generate_password_hash(password)
        )

        db.session.add(new_user)
        db.session.commit()

        flash(
            "Registration successful. Please login.",
            "success"
        )

        return redirect(url_for("login"))

    return render_template("register.html")


# ==========================================
# USER LOGIN
# ==========================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        email = request.form.get(
            "email", ""
        ).strip().lower()

        password = request.form.get("password", "")

        user = User.query.filter_by(
            email=email
        ).first()

        if user and check_password_hash(
            user.password, password
        ):

            login_user(user)

            flash("Login successful!", "success")

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("login.html")


# ==========================================
# USER LOGOUT
# ==========================================

@app.route("/logout")
@login_required
def logout():

    logout_user()

    flash("Logged out successfully.", "success")

    return redirect(url_for("login"))


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/dashboard")
@login_required
def dashboard():

    vehicles = Vehicle.query.count()

    records = FuelRecord.query.count()

    total_fuel = db.session.query(
        db.func.coalesce(
            db.func.sum(FuelRecord.fuel_liters),
            0
        )
    ).scalar()

    total_expense = db.session.query(
        db.func.coalesce(
            db.func.sum(FuelRecord.fuel_price),
            0
        )
    ).scalar()

    average_mileage = db.session.query(
        db.func.avg(
            FuelRecord.distance / FuelRecord.fuel_liters
        )
    ).filter(
        FuelRecord.fuel_liters > 0
    ).scalar()

    recent_records = (
        FuelRecord.query
        .join(Vehicle)
        .order_by(FuelRecord.fuel_date.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard/dashboard.html",
        vehicles=vehicles,
        records=records,
        total_fuel=round(total_fuel, 2),
        total_expense=round(total_expense, 2),
        average_mileage=round(average_mileage or 0, 2),
        recent_records=recent_records
    )


# ==========================================
# VEHICLE MANAGEMENT
# ==========================================

@app.route("/vehicles", methods=["GET", "POST"])
@login_required
def vehicles():

    if request.method == "POST":

        vehicle_number = request.form.get(
            "vehicle_number", ""
        ).strip().upper()

        vehicle_name = request.form.get(
            "vehicle_name", ""
        ).strip()

        vehicle_type = request.form.get(
            "vehicle_type", ""
        )

        fuel_type = request.form.get(
            "fuel_type", ""
        )

        if not all([
            vehicle_number,
            vehicle_name,
            vehicle_type,
            fuel_type
        ]):

            flash(
                "Please fill all vehicle details.",
                "danger"
            )

            return redirect(url_for("vehicles"))

        existing = Vehicle.query.filter_by(
            vehicle_number=vehicle_number
        ).first()

        if existing:

            flash(
                "Vehicle number already exists.",
                "danger"
            )

            return redirect(url_for("vehicles"))

        vehicle = Vehicle(
            vehicle_number=vehicle_number,
            vehicle_name=vehicle_name,
            vehicle_type=vehicle_type,
            fuel_type=fuel_type
        )

        db.session.add(vehicle)
        db.session.commit()

        flash(
            "Vehicle added successfully.",
            "success"
        )

        return redirect(url_for("vehicles"))

    all_vehicles = (
        Vehicle.query
        .order_by(Vehicle.id.desc())
        .all()
    )

    return render_template(
        "vehicles/vehicles.html",
        vehicles=all_vehicles
    )


# ==========================================
# DELETE VEHICLE
# ==========================================

@app.route(
    "/vehicles/delete/<int:vehicle_id>",
    methods=["POST"]
)
@login_required
def delete_vehicle(vehicle_id):

    vehicle = db.get_or_404(
        Vehicle,
        vehicle_id
    )

    if vehicle.fuel_records:

        flash(
            "Cannot delete vehicle with existing fuel records.",
            "danger"
        )

    else:

        db.session.delete(vehicle)
        db.session.commit()

        flash(
            "Vehicle deleted successfully.",
            "success"
        )

    return redirect(url_for("vehicles"))


# ==========================================
# FUEL RECORDS
# ==========================================

@app.route("/fuel-records", methods=["GET", "POST"])
@login_required
def fuel_records():

    all_vehicles = Vehicle.query.all()

    if request.method == "POST":

        try:

            vehicle_id = int(
                request.form.get("vehicle_id")
            )

            fuel_date = datetime.strptime(
                request.form.get("fuel_date"),
                "%Y-%m-%d"
            ).date()

            fuel_liters = float(
                request.form.get("fuel_liters")
            )

            fuel_price = float(
                request.form.get("fuel_price")
            )

            distance = float(
                request.form.get("distance")
            )

            vehicle = db.session.get(
                Vehicle,
                vehicle_id
            )

            if not vehicle:
                raise ValueError(
                    "Please select a valid vehicle."
                )

            if fuel_date > date.today():
                raise ValueError(
                    "Fuel date cannot be in the future."
                )

            if (
                fuel_liters <= 0
                or fuel_price < 0
                or distance <= 0
            ):
                raise ValueError(
                    "Enter valid fuel and distance values."
                )

            record = FuelRecord(
                vehicle_id=vehicle_id,
                fuel_date=fuel_date,
                fuel_liters=fuel_liters,
                fuel_price=fuel_price,
                distance=distance
            )

            db.session.add(record)
            db.session.commit()

            flash(
                "Fuel record added successfully.",
                "success"
            )

        except (ValueError, TypeError):

            db.session.rollback()

            flash(
                "Invalid fuel record details.",
                "danger"
            )

        return redirect(url_for("fuel_records"))

    records = (
        FuelRecord.query
        .join(Vehicle)
        .order_by(FuelRecord.fuel_date.desc())
        .all()
    )

    return render_template(
        "fuel/fuel_records.html",
        records=records,
        vehicles=all_vehicles,
        today=date.today().isoformat()
    )


# ==========================================
# DELETE FUEL RECORD
# ==========================================

@app.route(
    "/fuel-records/delete/<int:record_id>",
    methods=["POST"]
)
@login_required
def delete_fuel_record(record_id):

    record = db.get_or_404(
        FuelRecord,
        record_id
    )

    db.session.delete(record)
    db.session.commit()

    flash(
        "Fuel record deleted successfully.",
        "success"
    )

    return redirect(url_for("fuel_records"))


# ==========================================
# FUEL ANALYSIS
# ==========================================

@app.route("/fuel-analysis")
@login_required
def fuel_analysis():

    records = (
        FuelRecord.query
        .join(Vehicle)
        .order_by(FuelRecord.fuel_date.asc())
        .all()
    )

    monthly_data = {}

    for record in records:

        month = record.fuel_date.strftime("%Y-%m")

        if month not in monthly_data:

            monthly_data[month] = {
                "fuel": 0,
                "expense": 0,
                "distance": 0
            }

        monthly_data[month]["fuel"] += record.fuel_liters

        monthly_data[month]["expense"] += record.fuel_price

        monthly_data[month]["distance"] += record.distance

    return render_template(
        "analysis/fuel_analysis.html",
        records=records,
        monthly_data=monthly_data
    )


# ==========================================
# REPORTS PAGE
# ==========================================

@app.route("/reports")
@login_required
def reports():

    records = (
        FuelRecord.query
        .join(Vehicle)
        .order_by(FuelRecord.fuel_date.desc())
        .all()
    )

    total_fuel = sum(
        record.fuel_liters for record in records
    )

    total_expense = sum(
        record.fuel_price for record in records
    )

    return render_template(
        "reports/reports.html",
        records=records,
        total_fuel=round(total_fuel, 2),
        total_expense=round(total_expense, 2)
    )


# ==========================================
# EXPORT EXCEL REPORT
# ==========================================

@app.route("/export-excel")
@login_required
def export_excel():

    records = (
        FuelRecord.query
        .join(Vehicle)
        .order_by(FuelRecord.fuel_date.desc())
        .all()
    )

    workbook = Workbook()

    sheet = workbook.active

    sheet.title = "Fuel Report"

    sheet.append([
        "Vehicle Number",
        "Vehicle Name",
        "Fuel Date",
        "Fuel Litres",
        "Expense (INR)",
        "Distance (KM)",
        "Mileage (KM/L)"
    ])

    # Header formatting
    for cell in sheet[1]:

        cell.font = Font(
            bold=True,
            color="FFFFFF"
        )

        cell.fill = PatternFill(
            start_color="2563EB",
            end_color="2563EB",
            fill_type="solid"
        )

        cell.alignment = Alignment(
            horizontal="center"
        )

    # Add records
    for record in records:

        sheet.append([
            record.vehicle.vehicle_number,
            record.vehicle.vehicle_name,
            record.fuel_date.strftime("%d-%m-%Y"),
            record.fuel_liters,
            record.fuel_price,
            record.distance,
            round(record.mileage, 2)
        ])

    # Adjust column widths
    for column in sheet.columns:

        max_length = max(
            len(str(cell.value or ""))
            for cell in column
        )

        sheet.column_dimensions[
            column[0].column_letter
        ].width = max_length + 4

    output = BytesIO()

    workbook.save(output)

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="FuelTrack_Report.xlsx",
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )


# ==========================================
# EXPORT PDF REPORT
# ==========================================

@app.route("/export-pdf")
@login_required
def export_pdf():

    records = (
        FuelRecord.query
        .join(Vehicle)
        .order_by(FuelRecord.fuel_date.desc())
        .all()
    )

    output = BytesIO()

    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4)
    )

    styles = getSampleStyleSheet()

    elements = []

    elements.append(
        Paragraph(
            "FuelTrack - Fuel Consumption Report",
            styles["Title"]
        )
    )

    elements.append(
        Spacer(1, 20)
    )

    data = [[
        "Vehicle Number",
        "Vehicle Name",
        "Date",
        "Fuel (L)",
        "Expense (Rs.)",
        "Distance (KM)",
        "Mileage"
    ]]

    for record in records:

        data.append([
            record.vehicle.vehicle_number,
            record.vehicle.vehicle_name,
            record.fuel_date.strftime("%d-%m-%Y"),
            str(record.fuel_liters),
            str(record.fuel_price),
            str(record.distance),
            f"{record.mileage:.2f} km/L"
        ])

    table = Table(
        data,
        repeatRows=1
    )

    table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                colors.HexColor("#2563eb")
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold"
            ),
            (
                "GRID",
                (0, 0),
                (-1, -1),
                0.5,
                colors.grey
            ),
            (
                "ALIGN",
                (0, 0),
                (-1, -1),
                "CENTER"
            ),
            (
                "PADDING",
                (0, 0),
                (-1, -1),
                8
            ),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [
                    colors.white,
                    colors.HexColor("#eff6ff")
                ]
            )
        ])
    )

    elements.append(table)

    document.build(elements)

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="FuelTrack_Report.pdf",
        mimetype="application/pdf"
    )


# ==========================================
# DATABASE CREATION
# ==========================================

with app.app_context():
    db.create_all()


# ==========================================
# RUN APPLICATION
# ==========================================

if __name__ == "__main__":

    app.run(
        debug=True,
        port=5000
    )
