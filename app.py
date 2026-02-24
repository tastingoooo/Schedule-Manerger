from datetime import datetime, time, timedelta
from enum import StrEnum

import pandas as pd
import plotly.express as px
import streamlit as st

from db import (
    add_availability,
    create_schedule,
    delete_availability,
    delete_schedule,
    init_db,
    list_availabilities,
    list_schedules,
    update_availability,
    update_schedule,
)

st.set_page_config(page_title="多人排程管理", layout="wide")
init_db()

st.title("多人排程管理（Streamlit + SQLite）")
st.caption("可建立多個行程表，讓每個人填寫自己的可用時間，並以類甘特圖顯示")


class Profession(StrEnum):
    OPTION_1 = "黑騎士"
    OPTION_2 = "聖騎士"
    OPTION_3 = "英雄"
    OPTION_4 = "箭神"
    OPTION_5 = "神射手"
    OPTION_6 = "火毒"
    OPTION_7 = "冰雷"
    OPTION_8 = "主教"
    OPTION_9 = "拳霸"
    OPTION_10 = "槍神"
    OPTION_11 = "夜使者"
    OPTION_12 = "暗影神偷"


PROFESSION_OPTIONS = [profession.value for profession in Profession]


def combine_datetime(date_value, time_value) -> datetime:
    return datetime.combine(date_value, time_value)


def to_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda item: item[0])
    merged: list[tuple[datetime, datetime]] = [sorted_intervals[0]]

    for current_start, current_end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if current_start <= last_end:
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))

    return merged


def intersect_two_interval_lists(
    intervals_a: list[tuple[datetime, datetime]],
    intervals_b: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    intersections: list[tuple[datetime, datetime]] = []
    index_a, index_b = 0, 0

    while index_a < len(intervals_a) and index_b < len(intervals_b):
        start_a, end_a = intervals_a[index_a]
        start_b, end_b = intervals_b[index_b]

        intersection_start = max(start_a, start_b)
        intersection_end = min(end_a, end_b)

        if intersection_start < intersection_end:
            intersections.append((intersection_start, intersection_end))

        if end_a <= end_b:
            index_a += 1
        else:
            index_b += 1

    return intersections


def compute_common_availability(df: pd.DataFrame) -> list[tuple[datetime, datetime]]:
    merged_by_person = build_merged_intervals_by_person(df)
    if not merged_by_person:
        return []

    all_persons = list(merged_by_person.keys())
    common = merged_by_person[all_persons[0]]

    for person in all_persons[1:]:
        common = intersect_two_interval_lists(common, merged_by_person[person])
        if not common:
            break

    return common


def compute_min_people_availability(
    df: pd.DataFrame,
    required_people: int,
) -> list[dict[str, object]]:
    merged_by_person = build_merged_intervals_by_person(df)
    if len(merged_by_person) < required_people:
        return []

    events: list[tuple[datetime, str, str]] = []
    for person, intervals in merged_by_person.items():
        for start_dt, end_dt in intervals:
            events.append((start_dt, "start", person))
            events.append((end_dt, "end", person))

    if not events:
        return []

    events.sort(key=lambda item: (item[0], 0 if item[1] == "end" else 1))

    active_people: set[str] = set()
    index = 0
    previous_time: datetime | None = None
    result: list[dict[str, object]] = []

    while index < len(events):
        current_time = events[index][0]

        if (
            previous_time is not None
            and previous_time < current_time
            and len(active_people) >= required_people
        ):
            members = tuple(sorted(active_people))
            members_text = "、".join(members)
            if (
                result
                and result[-1]["end_dt"] == previous_time
                and result[-1]["available_members"] == members_text
            ):
                result[-1]["end_dt"] = current_time
            else:
                result.append(
                    {
                        "start_dt": previous_time,
                        "end_dt": current_time,
                        "available_members": members_text,
                        "available_count": len(members),
                    }
                )

        while index < len(events) and events[index][0] == current_time and events[index][1] == "end":
            active_people.discard(events[index][2])
            index += 1

        while index < len(events) and events[index][0] == current_time and events[index][1] == "start":
            active_people.add(events[index][2])
            index += 1

        previous_time = current_time

    return result


def build_merged_intervals_by_person(
    df: pd.DataFrame,
    selected_people: list[str] | None = None,
) -> dict[str, list[tuple[datetime, datetime]]]:
    person_to_intervals: dict[str, list[tuple[datetime, datetime]]] = {}
    selected_people_set = set(selected_people) if selected_people else None

    for _, row in df.iterrows():
        person = row["person_name"]
        if selected_people_set is not None and person not in selected_people_set:
            continue
        person_to_intervals.setdefault(person, []).append((row["start_dt"], row["end_dt"]))

    return {person: merge_intervals(intervals) for person, intervals in person_to_intervals.items()}


def compute_partial_group_overlaps(
    df: pd.DataFrame,
    selected_people: list[str],
    required_group_size: int,
) -> list[dict[str, object]]:
    merged_by_person = build_merged_intervals_by_person(df, selected_people)
    if len(merged_by_person) < required_group_size:
        return []

    events: list[tuple[datetime, str, str]] = []
    for person, intervals in merged_by_person.items():
        for start_dt, end_dt in intervals:
            events.append((start_dt, "start", person))
            events.append((end_dt, "end", person))

    if not events:
        return []

    events.sort(key=lambda item: (item[0], 0 if item[1] == "end" else 1))

    active_people: set[str] = set()
    partial_overlaps: list[dict[str, object]] = []
    index = 0
    previous_time: datetime | None = None

    while index < len(events):
        current_time = events[index][0]

        if (
            previous_time is not None
            and previous_time < current_time
            and len(active_people) >= required_group_size
        ):
            group_people = tuple(sorted(active_people))
            group_label = "、".join(group_people)
            if (
                partial_overlaps
                and partial_overlaps[-1]["group_label"] == group_label
                and partial_overlaps[-1]["end_dt"] == previous_time
            ):
                partial_overlaps[-1]["end_dt"] = current_time
            else:
                partial_overlaps.append(
                    {
                        "group_label": group_label,
                        "group_size": len(group_people),
                        "start_dt": previous_time,
                        "end_dt": current_time,
                        "members": group_people,
                    }
                )

        while index < len(events) and events[index][0] == current_time and events[index][1] == "end":
            active_people.discard(events[index][2])
            index += 1

        while index < len(events) and events[index][0] == current_time and events[index][1] == "start":
            active_people.add(events[index][2])
            index += 1

        previous_time = current_time

    return partial_overlaps


# ---------- Sidebar: Schedule CRUD ----------
st.sidebar.header("行程表管理")

with st.sidebar.form("create_schedule_form"):
    new_schedule_name = st.text_input(
        "新增行程表名稱",
        placeholder="例如：紅寶王",
        key="create_schedule_name",
    )
    new_schedule_desc = st.text_area(
        "描述（可選）",
        placeholder="例如：可能打散場",
        key="create_schedule_desc",
    )
    submitted_new_schedule = st.form_submit_button("新增行程表")

if submitted_new_schedule:
    if not new_schedule_name.strip():
        st.sidebar.error("行程表名稱不可為空")
    else:
        try:
            create_schedule(new_schedule_name, new_schedule_desc)
            st.sidebar.success("行程表已新增")
            st.rerun()
        except Exception as exc:
            st.sidebar.error(f"新增失敗：{exc}")

schedule_rows = list_schedules()

if not schedule_rows:
    st.info("目前還沒有行程表，請先在左側新增一個。")
    st.stop()

schedule_options = {f"{row['name']} (ID:{row['id']})": row for row in schedule_rows}
selected_schedule_label = st.sidebar.selectbox("選擇行程表", options=list(schedule_options.keys()))
selected_schedule = schedule_options[selected_schedule_label]
selected_schedule_id = selected_schedule["id"]

with st.sidebar.expander("編輯目前行程表"):
    with st.form("edit_schedule_form"):
        edit_name = st.text_input("行程表名稱", value=selected_schedule["name"])
        edit_desc = st.text_area("描述", value=selected_schedule["description"] or "")
        submitted_edit = st.form_submit_button("儲存行程表")

    if submitted_edit:
        if not edit_name.strip():
            st.error("行程表名稱不可為空")
        else:
            try:
                update_schedule(selected_schedule_id, edit_name, edit_desc)
                st.success("行程表已更新")
                st.rerun()
            except Exception as exc:
                st.error(f"更新失敗：{exc}")

    if st.button("刪除目前行程表", type="secondary"):
        delete_schedule(selected_schedule_id)
        st.success("行程表已刪除")
        st.rerun()


# ---------- Main: Availability CRUD ----------
st.subheader(f"行程表：{selected_schedule['name']}")
if selected_schedule["description"]:
    st.write(selected_schedule["description"])

st.markdown("### 新增可用時段")
with st.form("add_availability_form"):
    top_col1, top_col2 = st.columns(2)
    with top_col1:
        person_name = st.text_input("名稱", placeholder="例如：蠢羊", key="add_person_name")
    with top_col2:
        profession = st.selectbox("職業", options=PROFESSION_OPTIONS, key="add_profession")

    note = st.text_input("備註（可選）", placeholder="例如：不方便進語音", key="add_note")

    time_col1, time_col2 = st.columns(2)
    with time_col1:
        start_date = st.date_input("開始日期", key="add_start_date")
        start_clock = st.time_input(
            "開始時間",
            value=time(9, 0),
            step=timedelta(minutes=30),
            key="add_start_time",
        )
    with time_col2:
        if hasattr(st, "datetime_input"):
            end_dt_input = st.datetime_input(
                "結束日期時間",
                value=datetime.combine(datetime.now().date(), time(10, 0)),
                key="add_end_datetime",
            )
            end_date = end_dt_input.date()
            end_clock = end_dt_input.time().replace(second=0, microsecond=0)
        else:
            end_date = st.date_input("結束日期", key="add_end_date")
            end_clock = st.time_input(
                "結束時間",
                value=time(10, 0),
                step=timedelta(minutes=30),
                key="add_end_time",
            )

    submitted_availability = st.form_submit_button("新增可用時段")

if submitted_availability:
    start_dt = combine_datetime(start_date, start_clock)
    end_dt = combine_datetime(end_date, end_clock)

    if not person_name.strip():
        st.error("名稱不可為空")
    elif end_dt <= start_dt:
        st.error("結束時間必須晚於開始時間")
    else:
        add_availability(
            schedule_id=selected_schedule_id,
            person_name=person_name,
            profession=profession,
            start_time=start_dt.isoformat(),
            end_time=end_dt.isoformat(),
            note=note,
        )
        st.success("可用時段已新增")
        st.rerun()

availability_rows = list_availabilities(selected_schedule_id)

if not availability_rows:
    st.warning("這個行程表還沒有任何人填可用時段")
    st.stop()

availability_df = pd.DataFrame([dict(row) for row in availability_rows])
availability_df["start_dt"] = availability_df["start_time"].apply(to_datetime)
availability_df["end_dt"] = availability_df["end_time"].apply(to_datetime)
availability_df["start_display"] = availability_df["start_dt"].dt.strftime("%Y-%m-%d %H:%M")
availability_df["end_display"] = availability_df["end_dt"].dt.strftime("%Y-%m-%d %H:%M")

st.markdown("### 類甘特圖（所有人的可用時段）")
view_mode = st.radio(
    "圖表瀏覽方式",
    options=["單一總覽", "按天分段", "按週分段"],
    horizontal=True,
)

chart_df = availability_df.copy()
segment_title = ""

if view_mode == "按天分段":
    chart_df["segment_key"] = chart_df["start_dt"].dt.strftime("%Y-%m-%d")
    segment_options = sorted(chart_df["segment_key"].unique().tolist())
    selected_segment = st.selectbox("選擇日期", options=segment_options)
    chart_df = chart_df[chart_df["segment_key"] == selected_segment]
    segment_title = f"（{selected_segment}）"
elif view_mode == "按週分段":
    week_period = chart_df["start_dt"].dt.to_period("W-MON")
    chart_df["segment_key"] = week_period.apply(
        lambda item: f"{item.start_time.strftime('%Y-%m-%d')} ~ {item.end_time.strftime('%Y-%m-%d')}"
    )
    segment_options = sorted(chart_df["segment_key"].unique().tolist())
    selected_segment = st.selectbox("選擇週次", options=segment_options)
    chart_df = chart_df[chart_df["segment_key"] == selected_segment]
    segment_title = f"（{selected_segment}）"

fig = px.timeline(
    chart_df,
    x_start="start_dt",
    x_end="end_dt",
    y="person_name",
    color="person_name",
    hover_data={
        "person_name": True,
        "profession": True,
        "start_display": True,
        "end_display": True,
        "note": True,
        "start_dt": False,
        "end_dt": False,
    },
)
fig.update_yaxes(autorange="reversed", title_text="人員")
fig.update_xaxes(title_text=f"時間{segment_title}")
fig.update_layout(height=480, margin=dict(l=20, r=20, t=30, b=20))
st.plotly_chart(fig, use_container_width=True)

st.markdown("### 多人共同可用時段")
total_people = int(availability_df["person_name"].nunique())
min_slider_value = 3

if total_people < min_slider_value:
    st.info(f"目前人數不足 {min_slider_value} 人，無法使用此篩選。")
else:
    selected_min_people = st.slider(
        "最少同時有空人數",
        min_value=min_slider_value,
        max_value=total_people,
        value=min_slider_value,
    )

    common_intervals = compute_min_people_availability(
        availability_df,
        required_people=selected_min_people,
    )

    if not common_intervals:
        st.info(f"目前找不到至少 {selected_min_people} 人同時有空的時段")
    else:
        common_df = pd.DataFrame(common_intervals)
        common_df["start_display"] = common_df["start_dt"].dt.strftime("%Y-%m-%d %H:%M")
        common_df["end_display"] = common_df["end_dt"].dt.strftime("%Y-%m-%d %H:%M")

        common_gantt_df = common_df.copy()
        common_gantt_df["group"] = f"至少 {selected_min_people} 人共同可用"

        common_fig = px.timeline(
            common_gantt_df,
            x_start="start_dt",
            x_end="end_dt",
            y="group",
            color="group",
            hover_data={
                "start_display": True,
                "end_display": True,
                "available_count": True,
                "available_members": True,
                "start_dt": False,
                "end_dt": False,
                "group": False,
            },
        )
        common_fig.update_yaxes(autorange="reversed", title_text="")
        common_fig.update_xaxes(title_text="時間")
        common_fig.update_layout(height=220, margin=dict(l=20, r=20, t=20, b=20), showlegend=False)
        st.plotly_chart(common_fig, use_container_width=True)

        st.dataframe(
            common_df[["start_display", "end_display", "available_count", "available_members"]].rename(
                columns={
                    "start_display": "共同開始",
                    "end_display": "共同結束",
                    "available_count": "可用人數",
                    "available_members": "可用人員",
                }
            ),
            use_container_width=True,
        )

st.markdown("### 可用時段資料")
st.dataframe(
    availability_df[
        ["id", "person_name", "profession", "start_display", "end_display", "note", "created_at"]
    ]
    .rename(
        columns={
            "id": "時段ID",
            "person_name": "名稱",
            "profession": "職業",
            "start_display": "開始",
            "end_display": "結束",
            "note": "備註",
            "created_at": "建立時間",
        }
    ),
    use_container_width=True,
)

st.markdown("### 修改 / 刪除可用時段")
row_map = {
    f"ID {row['id']} | {row['person_name']} | {to_datetime(row['start_time']).strftime('%m/%d %H:%M')} - {to_datetime(row['end_time']).strftime('%m/%d %H:%M')}": row
    for row in availability_rows
}
selected_row_label = st.selectbox("選擇要修改或刪除的時段", options=list(row_map.keys()))
selected_row = row_map[selected_row_label]

selected_start = to_datetime(selected_row["start_time"])
selected_end = to_datetime(selected_row["end_time"])

with st.form("edit_availability_form"):
    top_ec1, top_ec2 = st.columns(2)
    with top_ec1:
        edit_person = st.text_input("名稱", value=selected_row["person_name"])
    with top_ec2:
        selected_profession = selected_row["profession"] or PROFESSION_OPTIONS[0]
        if selected_profession not in PROFESSION_OPTIONS:
            selected_profession = PROFESSION_OPTIONS[0]
        edit_profession = st.selectbox(
            "職業",
            options=PROFESSION_OPTIONS,
            index=PROFESSION_OPTIONS.index(selected_profession),
            key="edit_profession",
        )

    edit_note = st.text_input("備註（可選）", value=selected_row["note"] or "")

    time_ec1, time_ec2 = st.columns(2)
    with time_ec1:
        edit_start_date = st.date_input("開始日期", value=selected_start.date(), key="edit_start_date")
        edit_start_time = st.time_input(
            "開始時間",
            value=selected_start.time(),
            step=timedelta(minutes=30),
            key="edit_start_time",
        )
    with time_ec2:
        if hasattr(st, "datetime_input"):
            edit_end_dt_input = st.datetime_input(
                "結束日期時間",
                value=selected_end,
                key="edit_end_datetime",
            )
            edit_end_date = edit_end_dt_input.date()
            edit_end_time = edit_end_dt_input.time().replace(second=0, microsecond=0)
        else:
            edit_end_date = st.date_input("結束日期", value=selected_end.date(), key="edit_end_date")
            edit_end_time = st.time_input(
                "結束時間",
                value=selected_end.time(),
                step=timedelta(minutes=30),
                key="edit_end_time",
            )

    submitted_edit_availability = st.form_submit_button("儲存修改")

if submitted_edit_availability:
    edited_start_dt = combine_datetime(edit_start_date, edit_start_time)
    edited_end_dt = combine_datetime(edit_end_date, edit_end_time)

    if not edit_person.strip():
        st.error("名稱不可為空")
    elif edited_end_dt <= edited_start_dt:
        st.error("結束時間必須晚於開始時間")
    else:
        update_availability(
            availability_id=selected_row["id"],
            person_name=edit_person,
            profession=edit_profession,
            start_time=edited_start_dt.isoformat(),
            end_time=edited_end_dt.isoformat(),
            note=edit_note,
        )
        st.success("時段已更新")
        st.rerun()

if st.button("刪除這筆時段", type="secondary"):
    delete_availability(selected_row["id"])
    st.success("時段已刪除")
    st.rerun()
