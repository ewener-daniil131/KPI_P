import asyncio
import io
import mysql.connector
import matplotlib.pyplot as plt
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays a list of professors as buttons."""
    query = "SELECT id, full_name FROM professors;"
    data = fetch_data(query)

    if not data:
        await update.message.reply_text("Нет данных о преподавателях.")
        return

    keyboard = [[InlineKeyboardButton(professor[1], callback_data=f"professor_{professor[0]}")] for professor in data]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Выберите преподавателя:", reply_markup=reply_markup)


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles button interactions based on selected professor and actions."""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("professor_"):
        professor_id = query.data.split("professor_")[1]
        context.user_data['selected_professor'] = professor_id

        keyboard = [
            [InlineKeyboardButton("Пересчитать все KPI", callback_data="recalculate_kpi")],
            [InlineKeyboardButton("Отправить график", callback_data="choose_metric")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(f"Вы выбрали преподавателя с ID: {professor_id}.", reply_markup=reply_markup)

    elif query.data == "recalculate_kpi":
        await recalculate_kpi(update, context)

    elif query.data == "choose_metric":
        await choose_metric(update, context)

    elif query.data.startswith("metric_"):
        metric_name = query.data.split("metric_")[1]
        await send_graph(update, context, metric_name)


async def choose_metric(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetches metrics and displays them as buttons for graph generation."""
    metrics = [
        "lectures_count", "student_rating", "successful_students_percentage",
        "materials_published_count", "hours_worked", "capacity",
        "publications_count", "conferences_participated", "projects_applied_count",
        "tasks_completed", "project_involvement_count", "courses_completed",
        "new_methods_count", "awards_count", "university_events_participation_count"
    ]

    keyboard = [[InlineKeyboardButton(metric, callback_data=f"metric_{metric}")] for metric in metrics]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.callback_query.edit_message_text("Выберите метрику для графика:", reply_markup=reply_markup)


async def recalculate_kpi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recalculates KPI for the selected professor."""
    professor_id = context.user_data.get('selected_professor')
    if not professor_id:
        await update.callback_query.edit_message_text("Пожалуйста, выберите преподавателя сначала.")
        return

    query = f"""
    SELECT tm.lectures_count, tm.student_rating, tm.successful_students_percentage, tm.materials_published_count,
           wm.hours_worked, wm.capacity,
           rm.publications_count, rm.conferences_participated, rm.projects_applied_count,
           am.tasks_completed, am.project_involvement_count,
           dm.courses_completed, dm.new_methods_count,
           scm.awards_count, scm.university_events_participation_count
    FROM teaching_metrics tm
    LEFT JOIN workload_metrics wm ON tm.professor_id = wm.professor_id
    LEFT JOIN research_metrics rm ON tm.professor_id = rm.professor_id
    LEFT JOIN administrative_metrics am ON tm.professor_id = am.professor_id
    LEFT JOIN development_metrics dm ON tm.professor_id = dm.professor_id
    LEFT JOIN social_career_metrics scm ON tm.professor_id = scm.professor_id
    WHERE tm.professor_id = {professor_id};
    """
    data = fetch_data(query)

    if not data:
        await update.callback_query.edit_message_text("Нет данных для расчета KPI.")
        return

    kpi_results = {}
    metric_names = [
        "lectures_count", "student_rating", "successful_students_percentage",
        "materials_published_count", "hours_worked", "capacity",
        "publications_count", "conferences_participated", "projects_applied_count",
        "tasks_completed", "project_involvement_count", "courses_completed",
        "new_methods_count", "awards_count", "university_events_participation_count"
    ]

    for metric_name, value in zip(metric_names, data[0]):
        kpi_results[metric_name] = value if value is not None else 0

    response = f"Рассчитанные KPI для преподавателя с ID {professor_id}:"
    for metric, value in kpi_results.items():
        response += f"{metric}: {value:.2f}"

    await update.callback_query.edit_message_text(response)


async def send_graph(update: Update, context: ContextTypes.DEFAULT_TYPE, metric_name: str):
    """Generates and sends a graph for the selected metric."""
    professor_id = context.user_data.get('selected_professor')
    if not professor_id:
        await update.callback_query.edit_message_text("Пожалуйста, выберите преподавателя сначала.")
        return

    query = f"SELECT evaluation_date, {metric_name} FROM {get_table_for_metric(metric_name)} WHERE professor_id = {professor_id};"
    data = fetch_data(query)

    if not data:
        await update.callback_query.edit_message_text("Нет данных для построения графика.")
        return

    graph_buf = create_graph(data, metric_name)
    if graph_buf is None:
        await update.callback_query.edit_message_text("Не удалось создать график.")
        return

    await update.callback_query.message.reply_photo(photo=graph_buf)
    graph_buf.close()


def get_table_for_metric(metric_name: str) -> str:
    """Returns the appropriate table name for the given metric."""
    table_mapping = {
        "lectures_count": "teaching_metrics",
        "student_rating": "teaching_metrics",
        "successful_students_percentage": "teaching_metrics",
        "materials_published_count": "teaching_metrics",
        "hours_worked": "workload_metrics",
        "capacity": "workload_metrics",
        "publications_count": "research_metrics",
        "conferences_participated": "research_metrics",
        "projects_applied_count": "research_metrics",
        "tasks_completed": "administrative_metrics",
        "project_involvement_count": "administrative_metrics",
        "courses_completed": "development_metrics",
        "new_methods_count": "development_metrics",
        "awards_count": "social_career_metrics",
        "university_events_participation_count": "social_career_metrics",
    }
    return table_mapping.get(metric_name, "")


def fetch_data(query: str):
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="user",
            password="user_password",
            database="kpi_system"
        )
        cursor = conn.cursor()
        cursor.execute(query)
        data = cursor.fetchall()
        return data
    except mysql.connector.Error as err:
        print(f"Ошибка: {err}")
        return []
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()


def create_graph(data, metric_name: str):
    if not data:
        return None

    x, y = zip(*data)

    plt.figure(figsize=(12, 7))
    plt.plot(x, y, marker='o', color='teal', linestyle='--', linewidth=2, markersize=8, label=metric_name)
    plt.title(f'График по метрике: {metric_name}', fontsize=16, fontweight='bold')
    plt.xlabel('Дата', fontsize=12)
    plt.ylabel('Значение', fontsize=12)
    plt.xticks(rotation=45, fontsize=10)
    plt.yticks(fontsize=10)
    plt.legend(fontsize=12)
    plt.grid(visible=True, linestyle='--', linewidth=0.5, alpha=0.7)
    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf


def run_bot():
    TELEGRAM_TOKEN = ''

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    print("Бот запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


run_bot()
