import os
import json
import streamlit as st
import datetime
from datetime import timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import pytz

# --- Constants ---
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
TASKS_FILE = 'tasks.json'
TIMEZONE = 'America/New_York'  # Change to your timezone
calendar_events = []

# --- Initialize Session State ---
if "tasks" not in st.session_state:
    if os.path.exists(TASKS_FILE):
        with open(TASKS_FILE, 'r') as f:
            st.session_state.tasks = json.load(f)
    else:
        st.session_state.tasks = []

if "day_start_hour" not in st.session_state:
    st.session_state.day_start_hour = 8

if "day_end_hour" not in st.session_state:
    st.session_state.day_end_hour = 20

if "buffer_minutes" not in st.session_state:
    st.session_state.buffer_minutes = 5

# --- Google Calendar API Integration ---
def get_google_calendar_events():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('calendar', 'v3', credentials=creds)
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    end_of_day = (datetime.datetime.utcnow() + timedelta(hours=24)).isoformat() + 'Z'

    events_result = service.events().list(
        calendarId='primary', timeMin=now, timeMax=end_of_day,
        maxResults=20, singleEvents=True,
        orderBy='startTime').execute()

    events = events_result.get('items', [])
    return sorted(events, key=lambda e: e['start'].get('dateTime', e['start'].get('date')))

# --- Task Management ---
def save_tasks():
    with open(TASKS_FILE, 'w') as f:
        json.dump(st.session_state.tasks, f, default=str)

def add_task(title, priority, duration_minutes, category="General"):
    task = {
        "title": title,
        "priority": priority,
        "duration": duration_minutes,
        "category": category,
        "scheduled": False,
        "start_time": None,
        "end_time": None,
        "completed": False
    }
    st.session_state.tasks.append(task)
    save_tasks()

def delete_task(index):
    del st.session_state.tasks[index]
    save_tasks()

def edit_task(index, new_title, new_priority, new_duration, new_category):
    st.session_state.tasks[index]["title"] = new_title
    st.session_state.tasks[index]["priority"] = new_priority
    st.session_state.tasks[index]["duration"] = new_duration
    st.session_state.tasks[index]["category"] = new_category
    save_tasks()

def toggle_task_completion(index):
    st.session_state.tasks[index]["completed"] = not st.session_state.tasks[index]["completed"]
    save_tasks()

def get_prioritized_tasks():
    return sorted([task for task in st.session_state.tasks if not task["completed"]], 
                 key=lambda x: (x["priority"], -x["duration"]))

def find_free_slots(events, day_start, day_end):
    busy_slots = []
    for event in events:
        start_str = event['start'].get('dateTime')
        end_str = event['end'].get('dateTime')
        if start_str and end_str:
            start = datetime.datetime.fromisoformat(start_str[:-1]).astimezone(pytz.timezone(TIMEZONE))
            end = datetime.datetime.fromisoformat(end_str[:-1]).astimezone(pytz.timezone(TIMEZONE))
            busy_slots.append((start, end))

    busy_slots.sort()
    free_slots = []
    current = day_start

    for start, end in busy_slots:
        if current < start:
            free_slots.append((current, start))
        current = max(current, end)

    if current < day_end:
        free_slots.append((current, day_end))

    return free_slots

def schedule_tasks():
    day_start = datetime.datetime.combine(datetime.date.today(), 
                                        datetime.time(st.session_state.day_start_hour, 0)).astimezone(pytz.timezone(TIMEZONE))
    day_end = datetime.datetime.combine(datetime.date.today(), 
                                      datetime.time(st.session_state.day_end_hour, 0)).astimezone(pytz.timezone(TIMEZONE))
    
    if not calendar_events:
        st.warning("No calendar events found to schedule around")
        return
    
    free_slots = find_free_slots(calendar_events, day_start, day_end)
    free_slots.sort(key=lambda slot: (slot[1] - slot[0]), reverse=True)
    
    buffer_time = timedelta(minutes=st.session_state.buffer_minutes)
    
    for task in get_prioritized_tasks():
        if task["scheduled"]:
            continue
            
        task_duration = timedelta(minutes=task["duration"]) + buffer_time
        
        for i, (start, end) in enumerate(free_slots):
            slot_duration = end - start
            if task_duration <= slot_duration:
                task["scheduled"] = True
                task["start_time"] = start.isoformat()
                task["end_time"] = (start + task_duration).isoformat()
                
                # Update the free slot
                new_start = start + task_duration
                free_slots[i] = (new_start, end)
                if new_start >= end:
                    del free_slots[i]
                break
                
    save_tasks()

# --- Analytics ---
def calculate_productivity():
    total_tasks = len(st.session_state.tasks)
    completed_tasks = sum(1 for task in st.session_state.tasks if task["completed"])
    
    if total_tasks == 0:
        return 0, 0, 0
    
    completion_rate = (completed_tasks / total_tasks) * 100
    
    total_planned_time = sum(task["duration"] for task in st.session_state.tasks if task["scheduled"])
    actual_time = sum(task["duration"] for task in st.session_state.tasks if task["completed"])
    
    return completion_rate, total_planned_time, actual_time

# --- Streamlit UI ---
st.set_page_config(page_title="🧠 AI Time Coach", layout="wide")
st.title("🧠 AI Time Management Coach")

# Settings Panel
with st.sidebar:
    st.subheader("⚙️ Settings")
    st.session_state.day_start_hour = st.slider("Day Start Hour", 5, 12, 8)
    st.session_state.day_end_hour = st.slider("Day End Hour", 16, 23, 20)
    st.session_state.buffer_minutes = st.number_input("Buffer Between Tasks (minutes)", 0, 30, 5)
    
    # Productivity Stats
    completion_rate, planned_time, actual_time = calculate_productivity()
    st.subheader("📊 Productivity Stats")
    st.metric("Completion Rate", f"{completion_rate:.1f}%")
    st.metric("Planned Time", f"{planned_time} minutes")
    st.metric("Actual Time", f"{actual_time} minutes")

# Main Columns
col1, col2 = st.columns([1, 2])

with col1:
    # Add a Task
    with st.expander("➕ Add New Task", expanded=True):
        title = st.text_input("Task Name")
        col1a, col1b, col1c = st.columns(3)
        with col1a:
            priority = st.selectbox("Priority", [1, 2, 3], format_func=lambda x: {1: "High", 2: "Medium", 3: "Low"}[x])
        with col1b:
            duration = st.slider("Duration (min)", 15, 180, 30)
        with col1c:
            category = st.selectbox("Category", ["Work", "Personal", "Health", "Learning", "Other"])
        
        if st.button("Add Task"):
            if title.strip() == "":
                st.warning("⚠️ Task name can't be empty!")
            else:
                add_task(title, priority, duration, category)
                st.success("✅ Task added!")

    # Fetch Calendar
    with st.expander("📅 Google Calendar"):
        if st.button("Fetch Calendar Events"):
            calendar_events.clear()
            try:
                calendar_events.extend(get_google_calendar_events())
                if not calendar_events:
                    st.info("No upcoming events found.")
                else:
                    st.success(f"Found {len(calendar_events)} events")
            except Exception as e:
                st.error(f"❌ Failed to fetch calendar: {e}")

    # Smart Scheduler
    with st.expander("🧠 Smart Scheduler"):
        if st.button("Schedule Tasks Automatically"):
            if not calendar_events:
                st.warning("📅 Please fetch calendar first!")
            else:
                schedule_tasks()
                st.success("✅ Tasks scheduled into free time!")

with col2:
    # Task List
    st.subheader("📝 Your Tasks")
    
    if not st.session_state.tasks:
        st.info("No tasks yet. Add some tasks to get started!")
    else:
        for idx, task in enumerate(get_prioritized_tasks()):
            task_col1, task_col2, task_col3, task_col4 = st.columns([6, 1, 1, 1])
            with task_col1:
                if task.get("scheduled") and task.get("start_time"):
                    start_time = datetime.datetime.fromisoformat(task['start_time']).strftime('%H:%M')
                    end_time = datetime.datetime.fromisoformat(task['end_time']).strftime('%H:%M')
                    st.write(f"🗓 **{task['title']}** | ⏱ {start_time}-{end_time} | 🏷 {task['category']} | 🔢 {task['priority']}")
                else:
                    st.write(f"🕒 **{task['title']}** | ⏱ {task['duration']}min | 🏷 {task['category']} | 🔢 {task['priority']}")
            
            with task_col2:
                if st.button("✓", key=f"complete_{idx}"):
                    toggle_task_completion(idx)
                    st.experimental_rerun()
            
            with task_col3:
                if st.button("✏️", key=f"edit_{idx}"):
                    st.session_state.editing_task = idx
            
            with task_col4:
                if st.button("🗑️", key=f"del_{idx}"):
                    delete_task(idx)
                    st.experimental_rerun()
            
            if "editing_task" in st.session_state and st.session_state.editing_task == idx:
                with st.form(key=f"edit_form_{idx}"):
                    new_title = st.text_input("Title", value=task['title'], key=f"nt_{idx}")
                    new_priority = st.selectbox("Priority", [1, 2, 3], index=task['priority']-1, key=f"np_{idx}")
                    new_duration = st.slider("Duration (min)", 15, 180, task['duration'], key=f"nd_{idx}")
                    new_category = st.selectbox("Category", ["Work", "Personal", "Health", "Learning", "Other"], 
                                             index=["Work", "Personal", "Health", "Learning", "Other"].index(task['category']), 
                                             key=f"nc_{idx}")
                    
                    if st.form_submit_button("Save Changes"):
                        edit_task(idx, new_title, new_priority, new_duration, new_category)
                        del st.session_state.editing_task
                        st.experimental_rerun()
                
                    if st.form_submit_button("Cancel"):
                        del st.session_state.editing_task
                        st.experimental_rerun()

    # Visual Timeline
    st.subheader("🕓 Today's Timeline")
    if not any(task.get("scheduled") for task in st.session_state.tasks):
        st.info("No tasks scheduled yet. Use the Smart Scheduler to arrange your tasks.")
    else:
        timeline_html = "<div style='margin: 20px 0;'>"
        for task in sorted([t for t in st.session_state.tasks if t.get("scheduled")], 
                          key=lambda x: x['start_time']):
            start = datetime.datetime.fromisoformat(task['start_time'])
            end = datetime.datetime.fromisoformat(task['end_time'])
            
            color_map = {
                "Work": "#4285F4",
                "Personal": "#EA4335",
                "Health": "#34A853",
                "Learning": "#FBBC05",
                "Other": "#9E9E9E"
            }
            
            color = color_map.get(task['category'], "#9E9E9E")
            
            timeline_html += f"""
            <div style='background: {color}; color: white; padding: 10px; 
                        margin-bottom: 5px; border-radius: 5px; 
                        {"opacity: 0.6;" if task["completed"] else ""}'>
                <strong>{task['title']}</strong><br>
                {start.strftime('%H:%M')}-{end.strftime('%H:%M')} | 
                {task['duration']}min | Priority: {task['priority']}
            </div>
            """
        timeline_html += "</div>"
        st.markdown(timeline_html, unsafe_allow_html=True)

# Clear All Tasks
if st.button("🗑️ Clear All Tasks"):
    st.session_state.tasks.clear()
    save_tasks()
    st.success("All tasks cleared!")
    st.experimental_rerun()