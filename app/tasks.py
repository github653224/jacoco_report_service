import shutil
import threading
from apscheduler.triggers.cron import CronTrigger
import app
from app import scheduler
import os
import subprocess
from time import sleep
from app.models import Task


# 用于存储每个任务对应的锁对象，格式为 {task_id: threading.Lock()}
update_task_locks = {}

def execute_task_for_update_report(task_id):
    print("开始执行报告")
    if task_id not in update_task_locks:
        update_task_locks[task_id] = threading.Lock()

    lock = update_task_locks[task_id]
    if not lock.acquire(blocking=False):
        return  # 如果锁已被占用（任务正在执行），直接返回不执行任务
    print("报告目录为：=======》", app.REPORT_DIR)
    try:
        # 模拟执行任务
        subprocess.run([
            "java", "-jar", os.getenv("JACOCO_HOME") + "/lib/jacococli.jar", "dump",
            "--address", "127.0.0.1", "--port", "6300", "--destfile", app.REPORT_DIR+"testcase.exec"
        ])
        sleep(3)
        subprocess.run([
            "java", "-jar", os.getenv("JACOCO_HOME") + "/lib/jacococli.jar", "report",  app.REPORT_DIR+"testcase.exec",
            "--html",  app.HTML_REPORT_FOLDER, "--xml",  app.REPORT_DIR+"jacoco.xml", "--csv", app.REPORT_DIR+"jacoco.csv",
            "--classfiles", os.getenv("TARGET_HOME") + "/target/classes/",
            "--sourcefiles", os.getenv("TARGET_HOME") + "/src/main/java/"
        ])
        print("执行任务：", task_id)
    finally:
        lock.release()  # 无论任务执行成功与否，最终都要释放锁



clean_task_locks = {}
def clear_and_generate_report(task_id):
    print("开始清除报告：", task_id)
    if task_id not in clean_task_locks:
        clean_task_locks[task_id] = threading.Lock()

    lock = clean_task_locks[task_id]
    if not lock.acquire(blocking=False):  # 使用阻塞式获取锁，确保一定会拿到锁
        return  # 如果锁已被占用（任务正在执行），直接返回不执行任务

    try:
        # 清除历史测试报告文件及相关临时文件
        report_file = os.path.join(app.REPORT_DIR, "testcase.exec")
        xml_file = os.path.join(app.REPORT_DIR, "jacoco.xml")
        csv_file = os.path.join(app.REPORT_DIR, "jacoco.csv")
        # html_dir = os.path.join(app.HTML_REPORT_FOLDER, "")

        if os.path.exists(report_file):
            print("清除历史报告文件", report_file)
            os.remove(report_file)
        if os.path.exists(xml_file):
            os.remove(xml_file)
        if os.path.exists(csv_file):
            os.remove(csv_file)
        # if os.path.exists(html_dir):
        #     shutil.rmtree(html_dir)

        # 模拟执行任务生成新报告
        subprocess.run([
            "java", "-jar", os.getenv("JACOCO_HOME") + "/lib/jacococli.jar", "dump",
            "--address", "127.0.0.1", "--port", "6300", "--reset", "--destfile", report_file
        ])
        # sleep(3)
        subprocess.run([
            "java", "-jar", os.getenv("JACOCO_HOME") + "/lib/jacococli.jar", "report", report_file,
            "--html", app.HTML_REPORT_FOLDER, "--xml", xml_file, "--csv", csv_file,
            "--classfiles", os.getenv("TARGET_HOME") + "/target/classes/",
            "--sourcefiles", os.getenv("TARGET_HOME") + "/src/main/java/"
        ])
        print("清除并生成报告任务：", task_id)
    finally:
        lock.release()  # 无论任务执行成功与否，最终都要释放锁


# 每天启动时重新加载任务到调度器（可以在应用启动时调用这个函数）
def load_tasks_to_scheduler():
    tasks = Task.query.all()
    for task in tasks:
        try:
            trigger = CronTrigger.from_crontab(task.cron)
            # 根据任务类型添加不同的执行函数
            # if task.name.startswith("清除历史报告"):
            #     print("添加清除历史报告任务")
            #     scheduler.add_job(func=clear_and_generate_report, trigger=trigger, args=[task.id], id=str(task.id))
            # else:
            #     print("添加更新报告任务")
            #     scheduler.add_job(func=execute_task_for_update_report, trigger=trigger, args=[task.id], id=str(task.id))
            print("添加更新报告任务")
            scheduler.add_job(func=execute_task_for_update_report, trigger=trigger, args=[task.id], id=str(task.id))
        except:
            print(f"任务 {task.id} 的Cron表达式配置可能有误，无法添加到调度器")