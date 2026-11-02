import sqlite3
from datetime import date
from io import BytesIO

import pandas as pd
import plotly.express as px
import streamlit as st

from auth import authenticate
from db import DEFAULT_DB_PATH, connect, initialize
from services import (
    ValidationError,
    create_bill,
    create_contract,
    create_room,
    create_tenant,
    delete_room,
    end_contract,
    export_rows,
    get_active_contracts,
    get_bills,
    get_dashboard,
    get_reading,
    get_rooms,
    get_tenants,
    mark_bill_paid,
    save_reading,
    update_room,
    update_tenant,
)


st.set_page_config(
    page_title="Nhà trọ Hùng Phát",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded",
)

initialize()
DB_PATH = DEFAULT_DB_PATH

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 2rem;}
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8fafc, #eef2ff);
        border: 1px solid #e2e8f0;
        padding: 16px 18px;
        border-radius: 14px;
    }
    div[data-testid="stForm"] {
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 18px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def money(value):
    return f"{int(value or 0):,} đ".replace(",", ".")


def table(rows):
    if rows:
        st.dataframe(pd.DataFrame([dict(row) for row in rows]), width="stretch",
                     hide_index=True)
    else:
        st.info("Chưa có dữ liệu.")


def handle_action(action):
    try:
        action()
    except ValidationError as error:
        st.error(str(error))
    except sqlite3.IntegrityError as error:
        st.error(f"Dữ liệu bị trùng hoặc không hợp lệ: {error}")
    else:
        st.success("Đã lưu thành công.")
        st.rerun()


def login_page():
    st.title("🏠 Quản lý nhà trọ Hùng Phát")
    st.caption("Đăng nhập để quản lý phòng, hợp đồng và hóa đơn.")
    left, center, right = st.columns([1, 1.15, 1])
    with center:
        with st.form("login"):
            username = st.text_input("Tên đăng nhập")
            password = st.text_input("Mật khẩu", type="password")
            submitted = st.form_submit_button("Đăng nhập", type="primary",
                                              width="stretch")
        if submitted:
            user = authenticate(username, password, DB_PATH)
            if user is None:
                st.error("Tên đăng nhập hoặc mật khẩu không đúng.")
            else:
                st.session_state["user"] = user
                st.rerun()
        with st.expander("Tài khoản dùng thử"):
            st.write("**Chủ trọ:** `chu_hung` / `HungPhat@2026`")
            st.write("**Quản lý:** `chi_lan` / `Lan@2026`")
            st.caption("Đổi mật khẩu mẫu trước khi đưa ứng dụng lên môi trường thật.")


def dashboard_page():
    month, rooms, current, revenue, expiring = get_dashboard(DB_PATH)
    st.title("Tổng quan")
    st.caption(f"Khu trọ Hùng Phát · Số liệu hóa đơn tháng {month}")
    total_rooms = rooms["total"] or 0
    occupied = rooms["occupied"] or 0
    occupancy = occupied / total_rooms * 100 if total_rooms else 0
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Tổng số phòng", total_rooms)
    col2.metric("Đang cho thuê", occupied, f"{occupancy:.0f}% lấp đầy")
    col3.metric("Phòng trống", rooms["vacant"] or 0)
    col4.metric("Đã thu tháng này", money(current["collected"]))
    col5.metric("Còn phải thu", money(current["debt"]))

    st.subheader("Doanh thu đã thu theo tháng")
    if revenue:
        frame = pd.DataFrame([dict(row) for row in revenue])
        frame["Tháng"] = frame["month"]
        frame["Doanh thu"] = frame["revenue"]
        chart = px.bar(frame, x="Tháng", y="Doanh thu", text_auto=".2s",
                       color_discrete_sequence=["#4f46e5"])
        chart.update_layout(xaxis_title="", yaxis_title="VNĐ",
                            margin=dict(l=12, r=12, t=18, b=12))
        st.plotly_chart(chart, width="stretch")
    else:
        st.info("Chưa có hóa đơn để thống kê.")

    st.subheader("Hợp đồng sắp hết hạn trong 30 ngày")
    if expiring:
        table(expiring)
    else:
        st.caption("Không có hợp đồng sắp hết hạn.")

    with st.expander("Tải báo cáo hóa đơn Excel"):
        bills = export_rows(DB_PATH)
        if bills:
            output = BytesIO()
            frame = pd.DataFrame([dict(row) for row in bills])
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                frame.to_excel(writer, index=False, sheet_name="Hoa don")
            st.download_button(
                "Tải báo cáo .xlsx",
                data=output.getvalue(),
                file_name=f"bao-cao-hoa-don-{date.today():%Y-%m-%d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.caption("Chưa có hóa đơn để xuất báo cáo.")


def rooms_page():
    st.title("Quản lý phòng")
    rooms = get_rooms(DB_PATH)
    filter_status = st.selectbox("Lọc trạng thái", ["Tất cả", "Trống", "Đang thuê", "Bảo trì"])
    visible = [r for r in rooms if filter_status == "Tất cả" or r["status"] == filter_status]
    table(visible)

    with st.expander("Thêm phòng mới"):
        with st.form("add_room"):
            name = st.text_input("Mã phòng", placeholder="Ví dụ: P.121")
            room_type = st.selectbox("Loại phòng", ["Phòng đơn", "Phòng đôi"])
            price = st.number_input("Giá thuê mỗi tháng (đ)", min_value=0, step=100000)
            area = st.number_input("Diện tích (m²)", min_value=0.0, step=1.0)
            submitted = st.form_submit_button("Thêm phòng", type="primary")
        if submitted:
            handle_action(lambda: create_room(DB_PATH, name, room_type, price, area))

    if rooms:
        st.subheader("Cập nhật phòng")
        room_by_label = {f"{r['name']} · {r['status']}": r for r in rooms}
        selected_label = st.selectbox("Chọn phòng cần sửa", list(room_by_label))
        room = room_by_label[selected_label]
        with st.form("edit_room"):
            name = st.text_input("Mã phòng", value=room["name"])
            room_type = st.selectbox(
                "Loại phòng", ["Phòng đơn", "Phòng đôi"],
                index=0 if room["room_type"] == "Phòng đơn" else 1,
            )
            price = st.number_input("Giá thuê (đ)", min_value=0, step=100000,
                                    value=int(room["price"]))
            area = st.number_input("Diện tích (m²)", min_value=0.0, step=1.0,
                                   value=float(room["area"]))
            status_options = (["Đang thuê"] if room["status"] == "Đang thuê"
                              else ["Trống", "Bảo trì"])
            status = st.selectbox(
                "Trạng thái phòng", status_options,
                index=status_options.index(room["status"]),
            )
            save = st.form_submit_button("Lưu thay đổi")
        if save:
            handle_action(lambda: update_room(DB_PATH, room["id"], name,
                                               room_type, price, area, status))
        if room["status"] != "Đang thuê":
            if st.button("Xóa phòng đã chọn", key=f"delete_{room['id']}",
                         type="secondary"):
                handle_action(lambda: delete_room(DB_PATH, room["id"]))
        else:
            st.caption("Phòng đang thuê không thể xóa.")


def tenants_page():
    st.title("Người thuê")
    tenants = get_tenants(DB_PATH)
    table(tenants)
    with st.expander("Thêm người thuê"):
        with st.form("add_tenant"):
            full_name = st.text_input("Họ và tên")
            phone = st.text_input("Số điện thoại", max_chars=10)
            national_id = st.text_input("CCCD/CMND")
            hometown = st.text_input("Quê quán")
            submitted = st.form_submit_button("Lưu người thuê", type="primary")
        if submitted:
            handle_action(lambda: create_tenant(
                DB_PATH, full_name, phone, national_id, hometown
            ))
    if tenants:
        st.subheader("Cập nhật thông tin người thuê")
        tenant_options = {
            f"{tenant['full_name']} · {tenant['phone']} · #{tenant['id']}": tenant
            for tenant in tenants
        }
        selected = st.selectbox("Chọn người thuê", list(tenant_options))
        tenant = tenant_options[selected]
        with st.form("edit_tenant"):
            full_name = st.text_input("Họ và tên", value=tenant["full_name"])
            phone = st.text_input("Số điện thoại", value=tenant["phone"], max_chars=10)
            national_id = st.text_input("CCCD/CMND", value=tenant["national_id"])
            hometown = st.text_input("Quê quán", value=tenant["hometown"])
            submitted = st.form_submit_button("Lưu thông tin")
        if submitted:
            handle_action(lambda: update_tenant(
                DB_PATH, tenant["id"], full_name, phone, national_id, hometown
            ))


def contracts_page():
    st.title("Hợp đồng thuê")
    active = get_active_contracts(DB_PATH)
    table(active)
    rooms = [r for r in get_rooms(DB_PATH) if r["status"] == "Trống"]
    tenants = get_tenants(DB_PATH)
    with st.expander("Lập hợp đồng"):
        if not rooms or not tenants:
            st.info("Cần có ít nhất một phòng trống và một người thuê trước.")
        else:
            room_options = {f"{r['name']} · {money(r['price'])}/tháng": r
                            for r in rooms}
            tenant_options = {f"{t['full_name']} · {t['phone']}": t
                              for t in tenants}
            with st.form("new_contract"):
                room_label = st.selectbox("Phòng", list(room_options))
                tenant_label = st.selectbox("Người thuê", list(tenant_options))
                start = st.date_input("Ngày bắt đầu", value=date.today())
                has_expiry = st.checkbox("Hợp đồng có ngày hết hạn")
                expires_on = st.date_input("Ngày hết hạn", value=date.today(),
                                           key="contract_expiry") if has_expiry else None
                rent = st.number_input("Tiền thuê/tháng (đ)", min_value=0,
                                       step=100000,
                                       value=int(room_options[room_label]["price"]))
                deposit = st.number_input("Tiền cọc (đ)", min_value=0, step=100000)
                submitted = st.form_submit_button("Tạo hợp đồng", type="primary")
            if submitted:
                handle_action(lambda: create_contract(
                    DB_PATH, room_options[room_label]["id"],
                    tenant_options[tenant_label]["id"], start, rent, deposit,
                    expires_on,
                ))

    if active:
        st.subheader("Kết thúc hợp đồng")
        contracts = {f"{c['room_name']} · {c['tenant_name']}": c for c in active}
        label = st.selectbox("Hợp đồng cần kết thúc", list(contracts))
        contract = contracts[label]
        with st.form("end_contract"):
            ended = st.date_input("Ngày trả phòng", value=date.today())
            returned = st.number_input("Tiền cọc hoàn trả (đ)", min_value=0,
                                       max_value=int(contract["deposit"]),
                                       value=int(contract["deposit"]), step=100000)
            submitted = st.form_submit_button("Kết thúc và trả phòng")
        if submitted:
            handle_action(lambda: end_contract(
                DB_PATH, contract["id"], ended, returned
            ))


def readings_page():
    st.title("Ghi chỉ số điện nước")
    active = get_active_contracts(DB_PATH)
    if not active:
        st.info("Chưa có phòng đang thuê.")
        return
    rooms = {f"{c['room_name']} · {c['tenant_name']}": c for c in active}
    label = st.selectbox("Phòng", list(rooms))
    month_date = st.date_input("Tháng ghi chỉ số", value=date.today().replace(day=1))
    room = rooms[label]
    month = month_date.strftime("%Y-%m")
    existing = get_reading(DB_PATH, room["room_id"], month)
    with st.form("meter_reading"):
        electricity_old = st.number_input(
            "Điện đầu kỳ (kWh)", min_value=0.0, step=1.0,
            value=float(existing["electricity_old"]) if existing else 0.0,
        )
        electricity_new = st.number_input(
            "Điện cuối kỳ (kWh)", min_value=0.0, step=1.0,
            value=float(existing["electricity_new"]) if existing else 0.0,
        )
        water_old = st.number_input(
            "Nước đầu kỳ (m³)", min_value=0.0, step=1.0,
            value=float(existing["water_old"]) if existing else 0.0,
        )
        water_new = st.number_input(
            "Nước cuối kỳ (m³)", min_value=0.0, step=1.0,
            value=float(existing["water_new"]) if existing else 0.0,
        )
        submitted = st.form_submit_button("Lưu chỉ số", type="primary")
    if submitted:
        handle_action(lambda: save_reading(
            DB_PATH, room["room_id"], month, electricity_old, electricity_new,
            water_old, water_new,
        ))
    st.caption("Không thể sửa chỉ số của phòng đã có hóa đơn hoặc đã thanh toán.")


def bills_page():
    st.title("Hóa đơn và thanh toán")
    month_date = st.date_input("Tháng hóa đơn", value=date.today().replace(day=1),
                               key="bills_month")
    month = month_date.strftime("%Y-%m")
    active = get_active_contracts(DB_PATH)
    with st.expander("Lập hóa đơn tháng"):
        if not active:
            st.info("Chưa có phòng đang thuê.")
        else:
            rooms = {f"{c['room_name']} · {c['tenant_name']}": c for c in active}
            with st.form("new_bill"):
                label = st.selectbox("Phòng cần lập hóa đơn", list(rooms))
                electricity_rate = st.number_input(
                    "Đơn giá điện (đ/kWh)", min_value=0, value=3500, step=100
                )
                water_rate = st.number_input(
                    "Đơn giá nước (đ/m³)", min_value=0, value=12000, step=1000
                )
                service = st.number_input("Phí dịch vụ khác (đ)", min_value=0,
                                          step=10000)
                submitted = st.form_submit_button("Tính và tạo hóa đơn",
                                                  type="primary")
            if submitted:
                handle_action(lambda: create_bill(
                    DB_PATH, rooms[label]["room_id"], month, electricity_rate,
                    water_rate, service,
                ))

    rows = get_bills(DB_PATH, month=month)
    table(rows)
    unpaid = [row for row in rows if row["status"] == "Chưa thanh toán"]
    if unpaid:
        choices = {f"{row['room_name']} · {money(row['total'])}": row
                   for row in unpaid}
        label = st.selectbox("Hóa đơn cần xác nhận đã thu", list(choices))
        if st.button("Xác nhận thanh toán", type="primary"):
            handle_action(lambda: mark_bill_paid(DB_PATH, choices[label]["id"]))


def debts_page():
    st.title("Phòng còn nợ")
    rows = get_bills(DB_PATH, unpaid_only=True)
    table(rows)
    total_debt = sum(row["total"] for row in rows)
    st.metric("Tổng tiền còn phải thu", money(total_debt))


def main():
    user = st.session_state.get("user")
    if user is None:
        login_page()
        return

    st.sidebar.title("🏠 Hùng Phát")
    st.sidebar.write(f"Xin chào, **{user['full_name']}**")
    st.sidebar.caption("Chủ trọ" if user["role"] == "chu_tro" else "Người quản lý")
    pages = ["Tổng quan", "Phòng trọ", "Người thuê", "Hợp đồng",
             "Điện nước", "Hóa đơn", "Phòng còn nợ"]
    if user["role"] == "quan_ly":
        pages.remove("Tổng quan")
    page = st.sidebar.radio("Chức năng", pages)
    if st.sidebar.button("Đăng xuất", width="stretch"):
        st.session_state.pop("user", None)
        st.rerun()

    if page == "Tổng quan":
        dashboard_page()
    elif page == "Phòng trọ":
        rooms_page()
    elif page == "Người thuê":
        tenants_page()
    elif page == "Hợp đồng":
        contracts_page()
    elif page == "Điện nước":
        readings_page()
    elif page == "Hóa đơn":
        bills_page()
    else:
        debts_page()


main()
