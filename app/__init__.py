from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
import os

app = Flask(__name__, template_folder=os.path.join(os.getcwd(), 'templates'))
app.static_folder = 'static'
CORS(app)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['REPORT_FOLDER'] = 'jacoco/'
REPORT_DIR = app.config['REPORT_FOLDER']

app.config['TEMPLATES_AUTO_RELOAD'] = True

app.config['INI_REPORT'] = "ini_report/"
INI_REPORT = app.config['INI_REPORT']


app.config['HTML_REPORT_FOLDER'] = 'jacoco/jacoco_report/'
HTML_REPORT_FOLDER = app.config['HTML_REPORT_FOLDER']

app.config['REPORT_PORT'] = 8989
REPORT_PORT = app.config['REPORT_PORT']


db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# 定时任务调度器
scheduler = BackgroundScheduler()
scheduler.start()

# 导入路由模块，注册蓝图（如果使用蓝图的话，后续可优化添加）
from app.routes import *

# 导入任务相关函数，用于应用启动时加载任务到调度器
from app.tasks import load_tasks_to_scheduler

# 在应用启动时调用任务加载函数，确保任务能正常调度
with app.app_context():
    load_tasks_to_scheduler()

# 用户加载回调函数
@login_manager.user_loader
def load_user(user_id):
    from app.models import User
    return User.query.get(int(user_id))