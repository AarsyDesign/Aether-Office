# Todo App — MVP Test Project

Build a full-stack Todo application with the following features:

## Features
1. **User Authentication** — simple login/register (username + password, no email verification needed)
2. **Task Management** — create, read, update, delete tasks
3. **Task Status** — mark tasks as complete/incomplete
4. **Categories** — assign tasks to categories (Work, Personal, Shopping, Other)
5. **Deadlines** — set due dates for tasks, show overdue tasks
6. **Dashboard** — summary view: total tasks, completed, overdue, by category

## Technical Requirements
- **Frontend:** HTML + CSS + vanilla JavaScript (no frameworks)
- **Backend:** Python Flask
- **Database:** SQLite
- **Auth:** Session-based (Flask sessions)
- **Testing:** pytest for backend

## Constraints
- Single-page feel (use JavaScript to toggle views)
- Responsive design (mobile-friendly)
- Clean, minimal UI
- No external CSS frameworks (write custom CSS)
- All code must be runnable with `pip install flask` only

## Acceptance Criteria
1. User can register and log in
2. User can create a task with title, description, category, and deadline
3. User can edit task details
4. User can delete tasks
5. User can mark tasks as complete/incomplete
6. Dashboard shows task statistics
7. Overdue tasks are highlighted
8. Categories are selectable when creating/editing tasks
9. All data persists across page refreshes
10. Application runs with `python app.py` and works in browser
