import os
import subprocess
import time
from apscheduler.triggers.cron import CronTrigger
from flask import render_template, redirect, url_for, request, flash, jsonify, session, current_app
from flask_login import login_user, login_required, logout_user, current_user
from app import app, db, bcrypt, scheduler
from app.models import Task, User
from app.tasks import execute_task_for_update_report, clear_and_generate_report

@app.route('/')
def home():
    # 如果用户已经登录，重定向到任务列表页面
    if 'user_id' in session:
        return redirect(url_for('tasks'))
    # 否则，重定向到登录页面
    return redirect(url_for('login'))

# 注册路由
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('注册成功，请登录！', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

# 登录路由
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('tasks'))
        else:
            flash('用户名或密码错误！', 'danger')
            return redirect(url_for('login'))
    return render_template('login.html')

# 登出路由
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# 任务管理页面
@app.route('/tasks')
@login_required
def tasks():
    all_tasks = Task.query.all()  # 获取所有任务，而不是仅当前用户的任务
    return render_template('tasks.html', tasks=all_tasks, taskId=None)

# 添加任务
@app.route('/add_task', methods=['POST'])
@login_required
def add_task():
    current_user_obj = current_user
    if current_user_obj.username!= 'admin':
        flash('只有管理员用户才能添加任务！', 'danger')
        return redirect(url_for('tasks'))

    task_name = request.form['task_name']
    cron_expression = request.form['cron_expression']
    new_task = Task(
        name=task_name,
        cron=cron_expression,
        user_id=current_user.id
    )
    db.session.add(new_task)
    db.session.commit()

    # 添加到调度器
    trigger = CronTrigger.from_crontab(cron_expression)
    scheduler.add_job(func=execute_task_for_update_report, trigger=trigger, args=[new_task.id], id=str(new_task.id))

    flash('任务添加成功！', 'success')
    return redirect(url_for('tasks'))

# 删除任务
@app.route('/delete_task/<int:task_id>', methods=['POST'])
@login_required
def delete_task(task_id):
    task = Task.query.get(task_id)
    if task and task.user_id == current_user.id:
        # 从调度器中移除
        scheduler.remove_job(str(task_id))
        db.session.delete(task)
        db.session.commit()
        flash('任务删除成功！', 'success')
        return redirect(url_for('tasks'))
    else:
        flash('只有管理员用户才能删除任务！', 'danger')
        return redirect(url_for('tasks'))


# 编辑任务
@app.route('/edit_task/<int:task_id>', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    current_user_obj = current_user
    if current_user_obj.username!= 'admin':
        flash('只有管理员用户才能编辑任务！', 'danger')
        return redirect(url_for('tasks'))

    task = Task.query.get(task_id)
    if request.method == 'GET':
        return render_template('edit_task.html', task_id=task_id, task=task)
    elif request.method == 'POST':
        if task:
            new_name = request.form.get('task_name')
            new_cron = request.form.get('cron_expression')

            if new_name:
                task.name = new_name
            if new_cron:
                task.cron = new_cron

            # 先从调度器中移除旧任务配置
            scheduler.remove_job(str(task_id))
            # 根据新的Cron表达式重新添加任务到调度器
            if new_cron:
                trigger = CronTrigger.from_crontab(new_cron)
                scheduler.add_job(func=execute_task_for_update_report, trigger=trigger, args=[task_id], id=str(task_id))

            db.session.commit()
            flash('任务编辑成功！', 'success')
            return redirect(url_for('tasks'))
        else:
            flash('要编辑的任务不存在！', 'danger')
            return redirect(url_for('tasks'))



# 分别记录执行更新任务和清除任务的上次执行时间
run_task_last_execution_times = {}
clear_report_last_execution_times = {}


@app.route('/run_task/<int:task_id>')
@login_required
def run_task(task_id):
    current_time = time.time()
    last_execution_time = run_task_last_execution_times.get(task_id, 0)
    if current_time - last_execution_time < 10:  # 判断距离上次执行是否小于10秒
        flash('不能连续点击，请10秒之后重试', 'warning')
        return redirect(url_for('tasks'))

    # 执行更新报告任务逻辑
    execute_task_for_update_report(task_id)
    flash('任务已执行！', 'success')
    # 更新该任务的上次执行时间戳
    run_task_last_execution_times[task_id] = current_time
    return redirect(url_for('tasks'))


@app.route('/clear_report/<int:task_id>')
@login_required
def clear_report(task_id):
    current_user_obj = current_user
    if current_user_obj.username != 'admin':
        flash('只有管理员用户才能清除任务！', 'danger')
        return redirect(url_for('tasks'))

    current_time = time.time()
    last_execution_time = clear_report_last_execution_times.get(task_id, 0)
    if current_time - last_execution_time < 30:  # 判断距离上次执行是否小于30秒
        flash('不能连续点击，请30秒之后重试', 'warning')
        return redirect(url_for('tasks'))

    # 执行清除并生成报告任务逻辑，执行2次
    for _ in range(2):
        # time.sleep(2)
        clear_and_generate_report(task_id)
    flash('任务已执行！', 'success')
    # 更新该任务的上次执行时间戳
    clear_report_last_execution_times[task_id] = current_time
    return redirect(url_for('tasks'))

@app.route('/report', methods=['GET'])
@login_required
def report():
    print("进入 report")

    # 获取Flask应用正在使用的端口
    try:
        # 启动 HTTP 服务，若已运行则不会重复启动
        print("开始启动服务")
        from app.utils import REPORT_PORT, REPORT_DIR
        subprocess.Popen(
            ["python", "-m", "http.server", str(REPORT_PORT)],
            cwd=REPORT_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        report_url = f"http://127.0.0.1:{REPORT_PORT}"
        print(f"Report URL: {report_url}")  # 调试日志
        return jsonify({"url": report_url})
    except Exception as e:
        print(f"Error: {e}")  # 调试日志
        return jsonify({"error": "服务启动失败"}), 500