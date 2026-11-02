import re
import sqlite3
from datetime import date

from db import connect


class ValidationError(ValueError):
    pass


def _phone_is_valid(phone):
    return re.fullmatch(r"\d{10}", phone.strip()) is not None


def create_room(db_path, name, room_type, price, area):
    name = name.strip()
    if not name or price < 0 or area < 0:
        raise ValidationError("Vui lòng nhập tên phòng và giá/diện tích hợp lệ.")
    with connect(db_path) as connection:
        connection.execute(
            "INSERT INTO rooms (name, room_type, price, area) VALUES (?, ?, ?, ?)",
            (name, room_type, price, area),
        )


def update_room(db_path, room_id, name, room_type, price, area, status=None):
    if not name.strip() or price < 0 or area < 0:
        raise ValidationError("Thông tin phòng không hợp lệ.")
    with connect(db_path) as connection:
        current = connection.execute(
            "SELECT status FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
        if current is None:
            raise ValidationError("Không tìm thấy phòng.")
        status = status or current["status"]
        allowed_statuses = {"Trống", "Đang thuê", "Bảo trì"}
        if status not in allowed_statuses:
            raise ValidationError("Trạng thái phòng không hợp lệ.")
        if current["status"] == "Đang thuê" and status != "Đang thuê":
            raise ValidationError("Không thể đổi trạng thái phòng đang có người thuê.")
        if current["status"] != "Đang thuê" and status == "Đang thuê":
            raise ValidationError("Hãy lập hợp đồng để chuyển phòng sang Đang thuê.")
        connection.execute(
            """UPDATE rooms SET name = ?, room_type = ?, price = ?, area = ?,
               status = ? WHERE id = ?""",
            (name.strip(), room_type, price, area, status, room_id),
        )


def delete_room(db_path, room_id):
    with connect(db_path) as connection:
        room = connection.execute(
            "SELECT status FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
        if room is None:
            raise ValidationError("Không tìm thấy phòng.")
        if room["status"] == "Đang thuê":
            raise ValidationError("Không thể xóa phòng đang có người thuê.")
        if connection.execute(
            "SELECT 1 FROM contracts WHERE room_id = ? LIMIT 1", (room_id,)
        ).fetchone():
            raise ValidationError("Không thể xóa phòng đã có lịch sử hợp đồng.")
        if connection.execute(
            "SELECT 1 FROM bills WHERE room_id = ? LIMIT 1", (room_id,)
        ).fetchone():
            raise ValidationError("Không thể xóa phòng đã có hóa đơn lưu trữ.")
        connection.execute("DELETE FROM rooms WHERE id = ?", (room_id,))


def create_tenant(db_path, full_name, phone, national_id="", hometown=""):
    if not full_name.strip() or not _phone_is_valid(phone):
        raise ValidationError("Họ tên bắt buộc và số điện thoại phải có đúng 10 chữ số.")
    with connect(db_path) as connection:
        connection.execute(
            """INSERT INTO tenants (full_name, national_id, phone, hometown)
               VALUES (?, ?, ?, ?)""",
            (full_name.strip(), national_id.strip(), phone.strip(), hometown.strip()),
        )


def update_tenant(db_path, tenant_id, full_name, phone, national_id="", hometown=""):
    if not full_name.strip() or not _phone_is_valid(phone):
        raise ValidationError("Họ tên bắt buộc và số điện thoại phải có đúng 10 chữ số.")
    with connect(db_path) as connection:
        result = connection.execute(
            """UPDATE tenants SET full_name = ?, phone = ?, national_id = ?,
               hometown = ? WHERE id = ?""",
            (full_name.strip(), phone.strip(), national_id.strip(),
             hometown.strip(), tenant_id),
        )
        if result.rowcount != 1:
            raise ValidationError("Không tìm thấy người thuê.")


def create_contract(db_path, room_id, tenant_id, start_date, rent, deposit,
                    expires_on=None):
    if rent < 0 or deposit < 0:
        raise ValidationError("Tiền thuê và tiền cọc không được âm.")
    if expires_on and expires_on < start_date:
        raise ValidationError("Ngày hết hạn không thể trước ngày bắt đầu.")
    with connect(db_path) as connection:
        room = connection.execute(
            "SELECT status FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
        if room is None or room["status"] != "Trống":
            raise ValidationError("Phòng không tồn tại hoặc hiện không trống.")
        if not connection.execute(
            "SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)
        ).fetchone():
            raise ValidationError("Không tìm thấy người thuê.")
        connection.execute(
            """INSERT INTO contracts
               (room_id, tenant_id, start_date, expires_on, rent, deposit)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (room_id, tenant_id, start_date.isoformat(),
             expires_on.isoformat() if expires_on else None, rent, deposit),
        )
        connection.execute(
            "UPDATE rooms SET status = 'Đang thuê' WHERE id = ?", (room_id,)
        )


def end_contract(db_path, contract_id, end_date, deposit_returned):
    with connect(db_path) as connection:
        contract = connection.execute(
            "SELECT * FROM contracts WHERE id = ? AND status = 'Đang hiệu lực'",
            (contract_id,),
        ).fetchone()
        if contract is None:
            raise ValidationError("Hợp đồng không tồn tại hoặc đã kết thúc.")
        if deposit_returned < 0 or deposit_returned > contract["deposit"]:
            raise ValidationError("Tiền cọc hoàn trả phải nằm trong khoảng tiền cọc.")
        if end_date < date.fromisoformat(contract["start_date"]):
            raise ValidationError("Ngày kết thúc không thể trước ngày bắt đầu.")
        connection.execute(
            """UPDATE contracts SET status = 'Đã kết thúc', end_date = ?,
               deposit_returned = ? WHERE id = ?""",
            (end_date.isoformat(), deposit_returned, contract_id),
        )
        connection.execute(
            "UPDATE rooms SET status = 'Trống' WHERE id = ?", (contract["room_id"],)
        )


def save_reading(db_path, room_id, month, electricity_old, electricity_new,
                 water_old, water_new):
    if electricity_new < electricity_old or water_new < water_old:
        raise ValidationError("Chỉ số mới không được nhỏ hơn chỉ số cũ.")
    with connect(db_path) as connection:
        room = connection.execute(
            "SELECT status FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
        if room is None or room["status"] != "Đang thuê":
            raise ValidationError("Chỉ ghi chỉ số cho phòng đang có người thuê.")
        if connection.execute(
            "SELECT 1 FROM bills WHERE room_id = ? AND month = ? AND status = 'Đã thanh toán'",
            (room_id, month),
        ).fetchone():
            raise ValidationError("Hóa đơn đã thanh toán, không thể sửa chỉ số.")
        if connection.execute(
            "SELECT 1 FROM bills WHERE room_id = ? AND month = ?",
            (room_id, month),
        ).fetchone():
            raise ValidationError("Phòng đã có hóa đơn tháng này; không thể sửa chỉ số.")
        connection.execute(
            """INSERT INTO meter_readings
               (room_id, month, electricity_old, electricity_new, water_old, water_new)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(room_id, month) DO UPDATE SET
               electricity_old = excluded.electricity_old,
               electricity_new = excluded.electricity_new,
               water_old = excluded.water_old,
               water_new = excluded.water_new""",
            (room_id, month, electricity_old, electricity_new, water_old, water_new),
        )


def create_bill(db_path, room_id, month, electricity_rate, water_rate, service_amount=0):
    if min(electricity_rate, water_rate, service_amount) < 0:
        raise ValidationError("Đơn giá và phí dịch vụ không được âm.")
    with connect(db_path) as connection:
        contract = connection.execute(
            """SELECT * FROM contracts WHERE room_id = ?
               AND status = 'Đang hiệu lực'""",
            (room_id,),
        ).fetchone()
        reading = connection.execute(
            "SELECT * FROM meter_readings WHERE room_id = ? AND month = ?",
            (room_id, month),
        ).fetchone()
        if contract is None:
            raise ValidationError("Phòng chưa có hợp đồng đang hiệu lực.")
        if reading is None:
            raise ValidationError("Cần ghi chỉ số điện nước trước khi lập hóa đơn.")
        if connection.execute(
            "SELECT 1 FROM bills WHERE room_id = ? AND month = ?",
            (room_id, month),
        ).fetchone():
            raise ValidationError("Hóa đơn phòng trong tháng này đã tồn tại.")
        electricity = round(
            (reading["electricity_new"] - reading["electricity_old"]) * electricity_rate
        )
        water = round((reading["water_new"] - reading["water_old"]) * water_rate)
        rent = contract["rent"]
        total = rent + electricity + water + service_amount
        connection.execute(
            """INSERT INTO bills
               (room_id, contract_id, month, rent_amount, electricity_amount,
                water_amount, service_amount, total)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (room_id, contract["id"], month, rent, electricity, water,
             service_amount, total),
        )
        return total


def mark_bill_paid(db_path, bill_id):
    with connect(db_path) as connection:
        result = connection.execute(
            """UPDATE bills SET status = 'Đã thanh toán', paid_at = CURRENT_TIMESTAMP
               WHERE id = ? AND status = 'Chưa thanh toán'""",
            (bill_id,),
        )
        if result.rowcount != 1:
            raise ValidationError("Hóa đơn không tồn tại hoặc đã được thanh toán.")


def get_rooms(db_path):
    with connect(db_path) as connection:
        return connection.execute(
            """SELECT r.*, t.full_name AS tenant_name FROM rooms r
               LEFT JOIN contracts c ON c.room_id = r.id AND c.status = 'Đang hiệu lực'
               LEFT JOIN tenants t ON t.id = c.tenant_id ORDER BY r.name"""
        ).fetchall()


def get_tenants(db_path):
    with connect(db_path) as connection:
        return connection.execute(
            """SELECT t.*, r.name AS room_name FROM tenants t
               LEFT JOIN contracts c ON c.tenant_id = t.id AND c.status = 'Đang hiệu lực'
               LEFT JOIN rooms r ON r.id = c.room_id ORDER BY t.full_name"""
        ).fetchall()


def get_active_contracts(db_path):
    with connect(db_path) as connection:
        return connection.execute(
            """SELECT c.*, r.name AS room_name, t.full_name AS tenant_name
               FROM contracts c JOIN rooms r ON r.id = c.room_id
               JOIN tenants t ON t.id = c.tenant_id
               WHERE c.status = 'Đang hiệu lực' ORDER BY r.name"""
        ).fetchall()


def get_reading(db_path, room_id, month):
    with connect(db_path) as connection:
        return connection.execute(
            "SELECT * FROM meter_readings WHERE room_id = ? AND month = ?",
            (room_id, month),
        ).fetchone()


def get_bills(db_path, month=None, unpaid_only=False):
    conditions = []
    parameters = []
    if month:
        conditions.append("b.month = ?")
        parameters.append(month)
    if unpaid_only:
        conditions.append("b.status = 'Chưa thanh toán'")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with connect(db_path) as connection:
        return connection.execute(
            f"""SELECT b.*, r.name AS room_name, t.full_name AS tenant_name
                FROM bills b JOIN rooms r ON r.id = b.room_id
                JOIN contracts c ON c.id = b.contract_id
                JOIN tenants t ON t.id = c.tenant_id {where}
                ORDER BY b.month DESC, r.name""",
            parameters,
        ).fetchall()


def get_dashboard(db_path):
    month = date.today().strftime("%Y-%m")
    with connect(db_path) as connection:
        rooms = connection.execute(
            """SELECT COUNT(*) AS total,
               SUM(CASE WHEN status = 'Đang thuê' THEN 1 ELSE 0 END) AS occupied,
               SUM(CASE WHEN status = 'Trống' THEN 1 ELSE 0 END) AS vacant
               FROM rooms"""
        ).fetchone()
        month_data = connection.execute(
            """SELECT COALESCE(SUM(total), 0) AS billed,
               COALESCE(SUM(CASE WHEN status = 'Đã thanh toán' THEN total ELSE 0 END), 0) AS collected,
               COALESCE(SUM(CASE WHEN status = 'Chưa thanh toán' THEN total ELSE 0 END), 0) AS debt
               FROM bills WHERE month = ?""",
            (month,),
        ).fetchone()
        revenue = connection.execute(
            """SELECT month, SUM(CASE WHEN status = 'Đã thanh toán' THEN total ELSE 0 END)
               AS revenue FROM bills GROUP BY month ORDER BY month"""
        ).fetchall()
        expiring = connection.execute(
            """SELECT c.id, r.name AS room_name, t.full_name AS tenant_name,
               c.expires_on AS end_date FROM contracts c JOIN rooms r ON r.id = c.room_id
               JOIN tenants t ON t.id = c.tenant_id
               WHERE c.status = 'Đang hiệu lực' AND c.expires_on BETWEEN ? AND ?
               ORDER BY c.expires_on""",
            (date.today().isoformat(),
             date.fromordinal(date.today().toordinal() + 30).isoformat()),
        ).fetchall()
    return month, rooms, month_data, revenue, expiring


def export_rows(db_path):
    return get_bills(db_path)
