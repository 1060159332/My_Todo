import sys
import sqlite3
import ctypes
from datetime import datetime, timedelta
# 引入 PyQt6 界面库的核心组件
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QScrollArea, 
                             QLabel, QFrame, QGraphicsDropShadowEffect, QSlider, QCheckBox,
                             QCalendarWidget, QDialog, QTimeEdit, QColorDialog, QSizeGrip, 
                             QMenu, QSystemTrayIcon, QComboBox)
# 引入核心信号、时间、几何图形处理
from PyQt6.QtCore import Qt, pyqtSignal, QDateTime, QPoint, QTimer, QSize, QRect, QRectF
# 引入绘图工具（用于绘制自定义按钮、图标等）
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QCursor, QAction, QIcon, QPixmap

# ==========================================
# 1. 数据库管理模块 (Database Manager)
# 负责所有的数据增删改查
# ==========================================
class DatabaseManager:
    def __init__(self, db_name="todo_v20.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        """ 初始化数据库，如果表不存在则创建，如果字段缺失则自动升级 """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # 创建基础表结构
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                is_done INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 1,
                deadline TEXT,
                recurrence TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
         # [新增] 创建设置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        # 数据库迁移逻辑：检查旧版本的数据库是否缺少新功能的字段，如果缺少则补上
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'priority' not in columns: cursor.execute("ALTER TABLE tasks ADD COLUMN priority INTEGER DEFAULT 1")
        if 'deadline' not in columns: cursor.execute("ALTER TABLE tasks ADD COLUMN deadline TEXT")
        if 'recurrence' not in columns: cursor.execute("ALTER TABLE tasks ADD COLUMN recurrence TEXT")
        conn.commit()
        conn.close()

        # [新增] 获取设置
    def get_setting(self, key, default=None):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else default

    # [新增] 保存设置
    def set_setting(self, key, value):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
        conn.commit()
        conn.close()

    def add_task(self, content, priority, deadline_str, recurrence=None):
        """ 插入一条新任务 """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO tasks (content, priority, deadline, recurrence, is_done) VALUES (?, ?, ?, ?, 0)', 
                       (content, priority, deadline_str, recurrence))
        conn.commit()
        conn.close()

    def get_tasks(self):
        """ 
        获取所有任务并排序 
        排序逻辑：
        1. 未完成的任务排在前面 (is_done ASC)
        2. 高优先级的排在前面 (priority DESC)
        3. 没有设置截止日期的排在后面 (CASE WHEN...)
        4. 截止日期早的排在前面 (deadline ASC)
        5. 后创建的 ID 大，排在前面 (id DESC)
        """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, content, is_done, priority, deadline, recurrence
            FROM tasks 
            ORDER BY is_done ASC, priority DESC, 
                     CASE WHEN deadline = '' THEN 1 ELSE 0 END, 
                     deadline ASC, id DESC
        ''')
        tasks = cursor.fetchall()
        conn.close()
        return tasks

    def update_status(self, task_id, is_done):
        """ 更新任务是否完成 """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET is_done = ? WHERE id = ?', (1 if is_done else 0, task_id))
        conn.commit()
        conn.close()
    
    def get_task_by_id(self, task_id):
        """ 根据 ID 获取单条任务详情（用于重复任务生成逻辑） """
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('SELECT id, content, is_done, priority, deadline, recurrence FROM tasks WHERE id = ?', (task_id,))
        task = cursor.fetchone()
        conn.close()
        return task

    def delete_task(self, task_id):
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()

# ==========================================
# 2. 自定义 UI 组件 (Custom UI Components)
# 为了美观，这里重写了很多原生控件
# ==========================================

class CustomTrayMenu(QWidget):
    """ 
    完全自定义的系统托盘菜单
    使用 QWidget 模拟菜单，而不是原生的 QMenu，为了实现圆角和半透明效果 
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # 设置无边框窗口，且不显示阴影（我们自己画阴影）
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(2)
        
        # 菜单背景容器
        self.container = QFrame()
        self.container.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 45, 240);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 8px;
            }
        """)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(5, 5, 5, 5)
        self.container_layout.setSpacing(2)
        self.layout.addWidget(self.container)
        
        # 添加阴影，增加立体感
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(20)
        self.shadow.setColor(QColor(0,0,0,100))
        self.container.setGraphicsEffect(self.shadow)

    def add_action(self, text, callback, is_red=False):
        """ 向自定义菜单添加一个按钮 """
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 动态设置样式，支持红色警告色（用于退出按钮）
        text_color = "#FF5252" if is_red else "white"
        bg_hover = "rgba(255, 82, 82, 0.15)" if is_red else "rgba(255, 255, 255, 0.1)"
        
        btn.setStyleSheet(f"""
            QPushButton {{
                color: {text_color};
                background: transparent;
                border: none;
                border-radius: 4px;
                padding: 8px 15px;
                text-align: left;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
        """)
        btn.clicked.connect(callback)
        btn.clicked.connect(self.hide) # 点击后自动隐藏菜单
        self.container_layout.addWidget(btn)
        return btn

    def add_separator(self):
        """ 添加分割线 """
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: rgba(255,255,255,0.1); max-height: 1px; margin: 4px 0px;")
        self.container_layout.addWidget(line)

class CloseDialog(QDialog):
    """ 自定义关闭询问弹窗 """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.choice = None # 'minimize' or 'exit'
        self.remember = False
        
        layout = QVBoxLayout(self)
        
        # 背景容器
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #555;
                border-radius: 10px;
            }
            QLabel { color: white; font-size: 14px; }
            QCheckBox { color: #ccc; }
            QPushButton {
                background-color: #444; color: white; border: none; 
                padding: 8px 15px; border-radius: 5px; font-weight: bold;
            }
            QPushButton:hover { background-color: #555; }
            #ExitBtn { background-color: #FF5252; }
            #ExitBtn:hover { background-color: #ff6b6b; }
        """)
        v_layout = QVBoxLayout(container)
        
        lbl = QLabel("您希望如何关闭窗口？")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.chk_remember = QCheckBox("记住我的选择")
        
        btn_layout = QHBoxLayout()
        btn_min = QPushButton("最小化到托盘")
        btn_exit = QPushButton("退出程序")
        btn_exit.setObjectName("ExitBtn")
        
        btn_min.clicked.connect(lambda: self.done_choice('minimize'))
        btn_exit.clicked.connect(lambda: self.done_choice('exit'))
        
        btn_layout.addWidget(btn_min)
        btn_layout.addWidget(btn_exit)
        
        v_layout.addWidget(lbl)
        v_layout.addSpacing(10)
        v_layout.addLayout(btn_layout)
        v_layout.addSpacing(5)
        v_layout.addWidget(self.chk_remember, 0, Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(container)
        
        # 阴影
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0,0,0,150))
        container.setGraphicsEffect(shadow)

    def done_choice(self, choice):
        self.choice = choice
        self.remember = self.chk_remember.isChecked()
        self.accept()

class LongPressBtn(QPushButton):
    """ 
    长按按钮组件
    用于“锁定”功能，防止用户误点导致无法操作窗口。
    逻辑：按下鼠标开始计时，松开鼠标停止。只有按满x秒才触发信号。
    """
    long_press_triggered = pyqtSignal()

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.default_text = text
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 禁用焦点，防止虚线框
        
        self.timer = QTimer(self)
        self.timer.setInterval(1000) # 每1秒触发一次
        self.timer.timeout.connect(self.on_tick)
        self.counter = 0
        self.required_seconds = 2 # 需要按住几秒

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.counter = self.required_seconds
            self.setText(str(self.counter)) # 显示倒计时数字
            self.timer.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.timer.stop()
            self.setText(self.default_text) # 没按够时间，恢复图标
        super().mouseReleaseEvent(event)

    def on_tick(self):
        self.counter -= 1
        if self.counter > 0:
            self.setText(str(self.counter))
        else:
            # 时间到
            self.timer.stop()
            self.setText(self.default_text)
            self.long_press_triggered.emit() # 发射成功信号

    def update_icon_state(self, is_locked):
        """ 根据锁定状态改变外观（红色警示） """
        self.default_text = "🔒" if is_locked else "🔓"
        self.setText(self.default_text)
        if is_locked:
            self.setStyleSheet("background-color: rgba(244, 67, 54, 0.3); border: 1px solid rgba(244,67,54,0.5); font-weight: bold; border-radius: 5px;")
        else:
            self.setStyleSheet("background: transparent; border-radius: 5px; color: rgba(255,255,255,0.6); font-size: 14px;")

class CompleteBtn(QPushButton):
    """ 
    仿苹果 Reminders 的圆形勾选按钮
    使用 QPainter 手动绘制，完全替代原生 CheckBox，解决样式丑和弹窗Bug
    """
    def __init__(self, is_done=False, priority=1, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setChecked(is_done)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.priority = priority
        self.colors = {1: "#9E9E9E", 2: "#FFC107", 3: "#FF5252"} # 优先级颜色：灰、黄、红

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 绘制圆形轮廓
        rect = QRectF(self.rect().adjusted(2, 2, -2, -2))
        path = QPainterPath()
        path.addEllipse(rect)
        
        p_color = QColor(self.colors.get(self.priority, "#9E9E9E"))
        
        if self.isChecked():
            # 已完成：实心填充 + 白色勾号
            painter.fillPath(path, p_color)
            painter.setPen(Qt.PenStyle.NoPen)
            
            pen = QPen(Qt.GlobalColor.white)
            pen.setWidthF(2.0)
            painter.setPen(pen)
            
            # 绘制对勾坐标
            c = rect.center()
            painter.drawLine(QPoint(int(c.x()-4), int(c.y())), QPoint(int(c.x()-1), int(c.y()+3)))
            painter.drawLine(QPoint(int(c.x()-1), int(c.y()+3)), QPoint(int(c.x()+4), int(c.y()-3)))
        else:
            # 未完成：空心圆环
            pen = QPen(p_color)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

class PriorityButton(QPushButton):
    """ 旗帜按钮，点击切换优先级 """
    priority_changed = pyqtSignal(int)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.current_priority = 1 
        self.colors = {1: "#4CAF50", 2: "#FFC107", 3: "#F44336"} # 绿、黄、红
        self.clicked.connect(self.cycle_priority)
        self.update_style()

    def cycle_priority(self):
        self.current_priority = (self.current_priority % 3) + 1
        self.update_style()
        self.priority_changed.emit(self.current_priority)

    def update_style(self):
        color = self.colors[self.current_priority]
        self.setText("⚑")
        self.setStyleSheet(f"QPushButton {{ color: {color}; background: transparent; border: none; font-size: 18px; font-weight: bold; }} QPushButton:hover {{ background: rgba(255,255,255,0.08); border-radius: 15px; }}")

class TaskWidget(QFrame):
    """ 
    单个任务条目组件 
    包含：完成按钮、文本、截止时间、删除按钮
    """
    delete_requested = pyqtSignal(int)
    status_changed = pyqtSignal(int, bool)

    def __init__(self, t_id, content, is_done, priority, deadline, recurrence, parent=None):
        super().__init__(parent) # 重要：parent 防止幽灵窗口
        self.t_id = t_id
        self.content = content
        self.is_done = bool(is_done)
        self.priority = priority
        self.deadline = deadline
        self.recurrence = recurrence
        self.init_ui()

    def init_ui(self):
        self.setObjectName("TaskRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        
        self.check_btn = CompleteBtn(self.is_done, self.priority, parent=self)
        self.check_btn.clicked.connect(self.on_check)
        
        content_layout = QVBoxLayout()
        content_layout.setSpacing(3)
        
        self.lbl_content = QLabel(self.content, parent=self)
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.9); font-family: 'Segoe UI', sans-serif;")
        
        self.lbl_info = QLabel(parent=self)
        self.update_info_label()
        
        content_layout.addWidget(self.lbl_content)
        content_layout.addWidget(self.lbl_info)
        
        self.del_btn = QPushButton("✕", parent=self)
        self.del_btn.setFixedSize(24, 24)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.del_btn.setObjectName("DeleteBtn")
        self.del_btn.clicked.connect(lambda: self.delete_requested.emit(self.t_id))

        layout.addWidget(self.check_btn)
        layout.addLayout(content_layout, 1)
        layout.addWidget(self.del_btn)
        self.update_visual_state()

    def update_info_label(self):
        """ 更新任务下方的辅助信息（截止时间、重复图标） """
        text_parts = []
        style_color = "rgba(255,255,255,0.4)"
        
        if self.deadline:
            try:
                dt_dead = datetime.strptime(self.deadline, "%Y-%m-%d %H:%M")
                dt_now = datetime.now()
                time_str = ""
                
                if self.is_done:
                    time_str = f"{dt_dead.strftime('%m-%d')}"
                    style_color = "rgba(255,255,255,0.2)"
                else:
                    delta = dt_dead - dt_now
                    if delta.total_seconds() < 0:
                        time_str = f"已过期 {dt_dead.strftime('%m-%d %H:%M')}"
                        style_color = "#FF5252"
                    elif delta.days == 0:
                        hrs = int(delta.seconds / 3600)
                        mins = int((delta.seconds % 3600) / 60)
                        time_str = f"剩余 {hrs}小时{mins}分"
                        style_color = "#FFC107"
                    else:
                        time_str = f"{dt_dead.strftime('%m-%d %H:%M')} 截止"
                text_parts.append(time_str)
            except: pass

        if self.recurrence:
            text_parts.append("🔁")

        if text_parts:
            self.lbl_info.setText("  ".join(text_parts))
            self.lbl_info.setStyleSheet(f"color: {style_color}; font-size: 10px; font-weight: {'600' if style_color=='#FF5252' else 'normal'};")
            self.lbl_info.show()
        else:
            self.lbl_info.hide()

    def on_check(self):
        self.is_done = self.check_btn.isChecked()
        self.update_visual_state()
        self.status_changed.emit(self.t_id, self.is_done)

    def update_visual_state(self):
        """ 切换已完成/未完成的视觉效果（删除线、颜色变淡） """
        font = self.lbl_content.font()
        font.setStrikeOut(self.is_done)
        self.lbl_content.setFont(font)
        if self.is_done:
            self.lbl_content.setStyleSheet("color: rgba(255,255,255,0.3);")
        else:
            self.lbl_content.setStyleSheet("color: rgba(255,255,255,0.9);")
        self.update_info_label()

# ==========================================
# 3. 主窗口 (Main Window)
# ==========================================
class TodoAppV20(QMainWindow):
    # 阴影边距，用于预留空间绘制阴影
    SHADOW_WIDTH_PX = 30 
    
    # Windows API 常量 (用于实现点击穿透)
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x80000
    WS_EX_TRANSPARENT = 0x20
    
    # Windows API 常量 (用于实现置顶且不闪烁)
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOACTIVATE = 0x0010
    SWP_SHOWWINDOW = 0x0040
    SWP_FRAMECHANGED = 0x0020

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.is_mini_mode = False
        self.is_locked = False
        self.is_click_through = False
        self.is_settings_visible = False
        self.selected_deadline = ""
        self.selected_recurrence = None
        self.is_top_most = False
        self.show_completed = False 
        self.show_upcoming = False # 默认折叠计划任务
        
        self.bg_color_rgb = "30, 30, 35"
        self.opacity_val = 240
        
        self.init_ui()
        self.setup_tray()
        self.load_tasks()

    def init_ui(self):
        self.resize(390, 700)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 阴影特效
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(45)
        self.shadow.setColor(QColor(0, 0, 0, 120))

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        # 为阴影预留边距
        self.main_layout.setContentsMargins(self.SHADOW_WIDTH_PX, self.SHADOW_WIDTH_PX, self.SHADOW_WIDTH_PX, self.SHADOW_WIDTH_PX)
        
        self.container = QFrame()
        self.container.setObjectName("Container")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.container.setGraphicsEffect(self.shadow)
        self.main_layout.addWidget(self.container)

        self.setup_title_bar()
        self.setup_settings_panel()
        self.setup_mini_mode()
        self.setup_task_list()
        self.setup_input_area()
        
        # 缩放手柄
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(20, 20)
        self.size_grip.setStyleSheet("background: transparent;")
        self.size_grip.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.size_grip.raise_()
        
        self.apply_styles()

    def setup_tray(self):
        """ 初始化系统托盘 """
        self.tray_icon = QSystemTrayIcon(self)
        
        # 绘制托盘图标
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#4CAF50"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(2, 2, 28, 28)
        painter.setPen(QPen(Qt.GlobalColor.white, 3))
        painter.drawLine(8, 16, 14, 22)
        painter.drawLine(14, 22, 24, 10)
        painter.end()
        self.tray_icon.setIcon(QIcon(pixmap))
        
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        # 左键切换显示
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_visibility()
        # 右键弹出自定义菜单
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self.show_custom_tray_menu()

    def show_custom_tray_menu(self):
        """ 显示毛玻璃风格的托盘菜单 """
        if hasattr(self, 'tray_menu_widget') and self.tray_menu_widget.isVisible():
            self.tray_menu_widget.hide()
            return

        self.tray_menu_widget = CustomTrayMenu()
        
        self.tray_menu_widget.add_action("显示 / 隐藏", self.toggle_visibility)
        self.tray_menu_widget.add_separator()
        
        if self.is_click_through:
            self.tray_menu_widget.add_action("🔓 解锁窗口", lambda: self.set_window_click_through(False))
        else:
            self.tray_menu_widget.add_action("🔒 锁定窗口 (穿透)", lambda: self.set_window_click_through(True))
            
        self.tray_menu_widget.add_separator()
        self.tray_menu_widget.add_action("❌ 退出程序", QApplication.instance().quit, is_red=True)
        
        # 计算显示位置
        cursor_pos = QCursor.pos()
        screen = self.screen().availableGeometry()
        x, y = cursor_pos.x(), cursor_pos.y()
        w, h = 180, 160 
        
        if x + w > screen.right(): x -= w
        if y + h > screen.bottom(): y -= h 
        
        self.tray_menu_widget.move(x, y)
        self.tray_menu_widget.show()

    def toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    # --- Windows API 功能区 ---

    def _apply_click_through_style(self):
        """ 
        应用点击穿透样式 
        核心逻辑：使用 SetWindowLong 修改窗口属性为透明层 (WS_EX_TRANSPARENT)
        """
        hwnd = int(self.winId())
        try:
            styles = ctypes.windll.user32.GetWindowLongW(hwnd, self.GWL_EXSTYLE)
            if self.is_click_through:
                new_styles = styles | self.WS_EX_TRANSPARENT | self.WS_EX_LAYERED
            else:
                new_styles = styles & ~self.WS_EX_TRANSPARENT
            ctypes.windll.user32.SetWindowLongW(hwnd, self.GWL_EXSTYLE, new_styles)
            # 强制刷新 Frame
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 
                                              self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOACTIVATE | self.SWP_FRAMECHANGED)
        except: pass

    def set_window_click_through(self, enable):
        """ 设置是否开启穿透模式 """
        self.is_click_through = enable
        
        # 联动 UI 状态
        if enable and not self.is_locked:
            self.toggle_lock()
        elif not enable and self.is_locked:
            self.toggle_lock()
            
        self._apply_click_through_style()
        
        # 如果开启穿透，必须强制置顶，否则窗口无法被看到
        if enable:
            self._force_top_most(True)
        else:
            self._force_top_most(self.is_top_most)

    def _force_top_most(self, enable):
        """ 使用 Qt 原生方法强制置顶 (最稳健) """
        pos = self.pos() # 记住位置
        current_flags = self.windowFlags()
        if enable:
            new_flags = current_flags | Qt.WindowType.WindowStaysOnTopHint
        else:
            new_flags = current_flags & ~Qt.WindowType.WindowStaysOnTopHint
        
        if new_flags != current_flags:
            self.setWindowFlags(new_flags)
            self.show()
            self.move(pos) # 恢复位置，减少视觉跳动

    def toggle_top_most(self):
        """ 用户点击置顶按钮 """
        self.is_top_most = self.pin_btn.isChecked()
        if self.is_top_most:
            self.pin_btn.setStyleSheet("background-color: rgba(76, 175, 80, 0.3); border: 1px solid rgba(76,175,80,0.5);")
        else:
            self.pin_btn.setStyleSheet("")
        self._force_top_most(self.is_top_most)

    def toggle_lock(self):
        """ 切换锁定状态 """
        self.is_locked = not self.is_locked
        self.lock_btn.update_icon_state(self.is_locked)
        self.lock_btn.setChecked(self.is_locked)

        if self.is_locked:
            self.title_label.setText("ToDo (Locked)")
            # 隐藏干扰元素
            self.input_frame.hide()
            self.settings_panel.setVisible(False)
            self.settings_btn.setVisible(False)
            self.pin_btn.setVisible(False)
            self.mode_btn.setVisible(False)
            self.btn_min.setVisible(False)
            self.btn_close.setVisible(False)
            self.size_grip.setVisible(False)
            # 设置 Qt 层面鼠标穿透
            self.scroll_area.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.mini_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            # 触发 Windows 层面穿透
            self.set_window_click_through(True)
        else:
            self.title_label.setText("ToDo")
            if not self.is_mini_mode: self.input_frame.show()
            self.settings_btn.setVisible(True)
            self.pin_btn.setVisible(True)
            self.mode_btn.setVisible(True)
            self.btn_min.setVisible(True)
            self.btn_close.setVisible(True)
            self.size_grip.setVisible(True)
            self.scroll_area.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.mini_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.set_window_click_through(False)

    # --- UI 布局构建 ---

    def setup_task_list(self):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.tasks_container = QWidget()
        self.tasks_container.setStyleSheet("background: transparent;")
        self.tasks_layout_main = QVBoxLayout(self.tasks_container)
        self.tasks_layout_main.setContentsMargins(8, 8, 8, 8)
        self.tasks_layout_main.setSpacing(6)
        
        # 三大区域：活跃、计划、完成
        self.active_tasks_layout = QVBoxLayout()
        self.active_tasks_layout.setSpacing(6)
        
        self.upcoming_toggle_btn = self.create_foldable_header("计划中 (0)  ▸", self.toggle_upcoming_view)
        self.upcoming_widget = QWidget()
        self.upcoming_widget.setVisible(False)
        self.upcoming_tasks_layout = QVBoxLayout(self.upcoming_widget)
        self.upcoming_tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.upcoming_tasks_layout.setSpacing(6)
        
        self.completed_toggle_btn = self.create_foldable_header("已完成 (0)  ▸", self.toggle_completed_view)
        self.completed_widget = QWidget()
        self.completed_widget.setVisible(False)
        self.completed_tasks_layout = QVBoxLayout(self.completed_widget)
        self.completed_tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.completed_tasks_layout.setSpacing(6)
        
        self.tasks_layout_main.addLayout(self.active_tasks_layout)
        self.tasks_layout_main.addWidget(self.upcoming_toggle_btn)
        self.tasks_layout_main.addWidget(self.upcoming_widget)
        self.tasks_layout_main.addWidget(self.completed_toggle_btn)
        self.tasks_layout_main.addWidget(self.completed_widget)
        self.tasks_layout_main.addStretch()
        
        self.scroll_area.setWidget(self.tasks_container)
        self.container_layout.addWidget(self.scroll_area)

    def create_foldable_header(self, text, slot):
        btn = QPushButton(text)
        btn.setFlat(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet("""
            QPushButton { color: rgba(255,255,255,0.5); font-size: 12px; text-align: left; padding: 5px; border: none; font-weight: bold;}
            QPushButton:hover { color: rgba(255,255,255,0.8); background: rgba(255,255,255,0.05); border-radius: 4px; }
        """)
        btn.clicked.connect(slot)
        return btn

    def toggle_upcoming_view(self):
        self.show_upcoming = not self.show_upcoming
        self.upcoming_widget.setVisible(self.show_upcoming)
        arrow = "▾" if self.show_upcoming else "▸"
        base = self.upcoming_toggle_btn.text().split("  ")[0]
        self.upcoming_toggle_btn.setText(f"{base}  {arrow}")

    def toggle_completed_view(self):
        self.show_completed = not self.show_completed
        self.completed_widget.setVisible(self.show_completed)
        arrow = "▾" if self.show_completed else "▸"
        base = self.completed_toggle_btn.text().split("  ")[0]
        self.completed_toggle_btn.setText(f"{base}  {arrow}")

    def load_tasks(self):
        # 1. 清空当前界面上的所有任务条目
        for layout in [self.active_tasks_layout, self.upcoming_tasks_layout, self.completed_tasks_layout]:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()

        tasks = self.db.get_tasks()
        
        today_end = datetime.now().replace(hour=23, minute=59, second=59)
        
        first_valid_undone = None
        upcoming_count = 0
        completed_count = 0
        
        for task in tasks:
            # 创建任务组件
            widget = TaskWidget(*task, parent=self.tasks_container)
            widget.status_changed.connect(self.on_status_change)
            widget.delete_requested.connect(self.on_delete)
            
            is_done = task[2]
            deadline_str = task[4]
            recurrence = task[5]
            
            if is_done:
                # 已完成任务 -> 放入底部折叠区
                self.completed_tasks_layout.addWidget(widget)
                completed_count += 1
            else:
                # --- 分流逻辑：活跃任务 vs 计划任务 ---
                is_upcoming = False
                
                # 只有同时满足 [未来时间] AND [是重复任务] 才会被归入"计划中"折叠区
                # 这样可以防止自动生成的重复任务刷屏
                if deadline_str and recurrence:
                    try:
                        dt = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
                        if dt > today_end:
                            is_upcoming = True
                    except: pass
                
                if is_upcoming:
                    # 放入中间折叠区
                    self.upcoming_tasks_layout.addWidget(widget)
                    upcoming_count += 1
                else:
                    # 放入主列表（活跃区域）
                    # 这里包含：今天任务、过期任务、无日期任务、以及【未来的非重复任务】
                    self.active_tasks_layout.addWidget(widget)
                    
                    # [修复] 极简模式逻辑优化
                    # 只要是主列表里的第一个任务，就应该在极简模式显示
                    # 不再额外判断日期，因为不需要显示的已经被分流到 is_upcoming 了
                    if not first_valid_undone: 
                        first_valid_undone = task
        
        # 更新折叠按钮文字
        arrow_up = "▾" if self.show_upcoming else "▸"
        self.upcoming_toggle_btn.setText(f"循环计划 ({upcoming_count})  {arrow_up}")
        self.upcoming_toggle_btn.setVisible(upcoming_count > 0)
        
        arrow_comp = "▾" if self.show_completed else "▸"
        self.completed_toggle_btn.setText(f"已完成 ({completed_count})  {arrow_comp}")
        self.completed_toggle_btn.setVisible(completed_count > 0)
        
        # 更新极简模式显示
        self.update_mini_display(first_valid_undone)

    # --- 其他核心逻辑 ---

    def on_status_change(self, t_id, is_done):
        if is_done:
            task = self.db.get_task_by_id(t_id)
            recurrence = task[5]
            if recurrence:
                try:
                    # 增强的重复逻辑：以当前时间为基础生成下一次
                    base_date = datetime.now()
                    if task[4]: # 如果原任务有具体时间，则尽量保持时间点
                        old_dt = datetime.strptime(task[4], "%Y-%m-%d %H:%M")
                        # 如果原定时间还没到，就基于原定时间；如果过期了，基于现在
                        if old_dt > base_date: base_date = old_dt
                    
                    new_deadline = base_date
                    if recurrence == 'daily': new_deadline += timedelta(days=1)
                    elif recurrence == 'weekly': new_deadline += timedelta(weeks=1)
                    elif recurrence == 'monthly': new_deadline += timedelta(days=30)
                    elif recurrence == 'yearly': new_deadline = new_deadline.replace(year=new_deadline.year + 1)
                    elif recurrence == 'workdays':
                        wd = new_deadline.weekday()
                        if wd == 4: new_deadline += timedelta(days=3)
                        elif wd == 5: new_deadline += timedelta(days=2)
                        else: new_deadline += timedelta(days=1)
                    
                    self.db.add_task(task[1], task[3], new_deadline.strftime("%Y-%m-%d %H:%M"), recurrence)
                except: pass
        self.db.update_status(t_id, is_done)
        self.load_tasks()

    # (Setup 代码与 V19 保持一致，这里省略重复部分，请直接使用上面的 apply_styles, setup_title_bar 等)
    def setup_title_bar(self):
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(46)
        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(16, 0, 12, 0)
        self.title_label = QLabel("ToDo")
        self.title_label.setStyleSheet("color: rgba(255,255,255,0.95); font-weight: 700; font-size: 15px;")
        self.pin_btn = self.create_title_btn("📌", "置顶窗口")
        self.pin_btn.clicked.connect(self.toggle_top_most)
        self.lock_btn = LongPressBtn("🔓", parent=self.title_bar)
        self.lock_btn.setToolTip("长按 5 秒锁定/解锁")
        self.lock_btn.long_press_triggered.connect(self.toggle_lock)
        self.lock_btn.setObjectName("TitleBtn")
        self.settings_btn = self.create_title_btn("⚙", "设置")
        self.settings_btn.clicked.connect(self.toggle_settings)
        self.mode_btn = self.create_title_btn("⛶", "极简模式")
        self.mode_btn.clicked.connect(self.toggle_mode)
        self.btn_min = self.create_title_btn("－", "最小化")
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_close = self.create_title_btn("✕", "关闭")
        self.btn_close.clicked.connect(self.close)
        self.btn_close.setObjectName("CloseBtn")
        layout.addWidget(self.title_label)
        layout.addStretch()
        layout.addWidget(self.pin_btn)
        layout.addWidget(self.lock_btn)
        layout.addWidget(self.settings_btn)
        layout.addWidget(self.mode_btn)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_close)
        self.container_layout.addWidget(self.title_bar)

    def create_title_btn(self, text, tooltip):
        btn = QPushButton(text)
        btn.setFixedSize(30, 30)
        btn.setCheckable(True) if text in ["📌"] else None
        btn.setToolTip(tooltip)
        btn.setObjectName("TitleBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def setup_settings_panel(self):
        self.settings_panel = QFrame()
        self.settings_panel.setVisible(False)
        self.settings_panel.setStyleSheet("background-color: rgba(0,0,0,0.15); border-bottom: 1px solid rgba(255,255,255,0.05);")
        
        layout = QVBoxLayout(self.settings_panel)
        layout.setContentsMargins(20, 15, 20, 15)
        layout.setSpacing(15) # 增加间距

        # 1. 透明度行
        h_op = QHBoxLayout()
        lbl_op = QLabel("透明度")
        lbl_op.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(50, 255)
        self.opacity_slider.setValue(240)
        self.opacity_slider.valueChanged.connect(self.change_opacity)
        h_op.addWidget(lbl_op)
        h_op.addWidget(self.opacity_slider)

        # 2. 颜色选择行
        h_col = QHBoxLayout()
        lbl_col = QLabel("主题色")
        lbl_col.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        btn_dark = self.create_color_btn("30, 30, 35", "#222")
        btn_blue = self.create_color_btn("30, 40, 60", "#2d4059")
        btn_purple = self.create_color_btn("50, 30, 60", "#4b2c50")
        btn_custom = QPushButton("🎨")
        btn_custom.setFixedSize(22, 22)
        btn_custom.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_custom.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_custom.clicked.connect(self.pick_custom_color)
        btn_custom.setStyleSheet("background: transparent; border: none;")
        
        h_col.addWidget(lbl_col)
        h_col.addSpacing(15)
        h_col.addWidget(btn_dark)
        h_col.addWidget(btn_blue)
        h_col.addWidget(btn_purple)
        h_col.addWidget(btn_custom)
        h_col.addStretch()

        # 3. [新增] 退出模式选择行
        h_close = QHBoxLayout()
        lbl_close = QLabel("关闭时")
        lbl_close.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        
        self.combo_close = QComboBox()
        self.combo_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.combo_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_close.addItems(["每次询问", "最小化到托盘", "退出程序"])
        
        # 美化下拉框
        self.combo_close.setStyleSheet("""
            QComboBox {
                background-color: rgba(255,255,255,0.1);
                color: white;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px;
                padding: 2px 10px;
                font-size: 11px;
                min-width: 80px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background-color: #333;
                color: white;
                selection-background-color: #4CAF50;
                border: 1px solid #555;
            }
        """)
        
        # 读取当前设置并更新 UI
        current_setting = self.db.get_setting("close_action")
        if current_setting == "minimize":
            self.combo_close.setCurrentIndex(1)
        elif current_setting == "exit":
            self.combo_close.setCurrentIndex(2)
        else:
            self.combo_close.setCurrentIndex(0)
            
        # 连接信号
        self.combo_close.currentIndexChanged.connect(self.on_close_option_changed)
        
        h_close.addWidget(lbl_close)
        h_close.addWidget(self.combo_close)
        h_close.addStretch()

        # 添加到主布局
        layout.addLayout(h_op)
        layout.addLayout(h_col)
        layout.addLayout(h_close)
        
        self.container_layout.addWidget(self.settings_panel)

    # [新增] 处理下拉框变化
    def on_close_option_changed(self, index):
        val = ""
        if index == 1: val = "minimize"
        elif index == 2: val = "exit"
        # index 0 (询问) 对应空字符串或特定标识，这里设为空字符串让 closeEvent 触发弹窗
        
        self.db.set_setting("close_action", val)

    def create_color_btn(self, rgb, hex_code):
        btn = QPushButton()
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet(f"background-color: {hex_code}; border: 1.5px solid rgba(255,255,255,0.3); border-radius: 11px;")
        btn.clicked.connect(lambda: self.change_bg_color(rgb))
        return btn

    def setup_mini_mode(self):
        self.mini_widget = QFrame()
        self.mini_widget.setVisible(False)
        self.mini_widget.setFixedHeight(50)
        layout = QHBoxLayout(self.mini_widget)
        layout.setContentsMargins(20, 0, 20, 0)
        self.mini_check = CompleteBtn(parent=self.mini_widget)
        self.mini_check.clicked.connect(self.complete_mini_task)
        self.mini_label = QLabel("暂无任务")
        self.mini_label.setStyleSheet("color: white; font-size: 14px; font-weight: 500;")
        layout.addWidget(self.mini_check)
        layout.addWidget(self.mini_label, 1)
        self.container_layout.addWidget(self.mini_widget)

    def setup_input_area(self):
        self.input_frame = QFrame()
        self.input_frame.setFixedHeight(70)
        self.input_frame.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self.input_frame)
        layout.setContentsMargins(16, 5, 25, 20)
        capsule = QFrame()
        capsule.setObjectName("InputCapsule")
        capsule_layout = QHBoxLayout(capsule)
        capsule_layout.setContentsMargins(8, 4, 8, 4)
        self.flag_btn = PriorityButton(parent=capsule)
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("添加新任务...")
        self.input_line.setStyleSheet("border: none; color: white; background: transparent; font-size: 13px;")
        self.input_line.returnPressed.connect(self.add_task_handler)
        self.input_line.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.lbl_deadline_preview = QLabel("")
        self.lbl_deadline_preview.setStyleSheet("color: #4CAF50; font-size: 11px; margin-right: 6px; font-weight: bold;")
        
        # 修复 UI：移除箭头占位符
        self.repeat_btn = QPushButton("🔁", parent=capsule)
        self.repeat_btn.setFixedSize(28, 28)
        self.repeat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.repeat_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.repeat_btn.setStyleSheet("""
            QPushButton { border: none; color: #888; border-radius: 4px; padding: 0px; text-align: center; } 
            QPushButton:hover { color: white; background: rgba(255,255,255,0.1); }
            QPushButton::menu-indicator { width: 0px; image: none; }
        """)
        self.repeat_btn.setToolTip("设置重复")
        
        self.repeat_menu = QMenu(self)
        self.repeat_menu.setStyleSheet("""
            QMenu { background-color: #2d2d2d; color: #ddd; border: 1px solid #444; border-radius: 8px; padding: 5px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: #4CAF50; color: white; }
        """)
        actions = [("每天", "daily"), ("每个工作日", "workdays"), ("每周", "weekly"), ("每月", "monthly"), ("每年", "yearly")]
        for name, value in actions:
            action = QAction(name, self)
            action.triggered.connect(lambda checked, v=value, n=name: self.set_recurrence(v, n))
            self.repeat_menu.addAction(action)
        self.repeat_btn.setMenu(self.repeat_menu)
        
        self.date_btn = QPushButton("⏰", parent=capsule)
        self.date_btn.setFixedSize(28, 28)
        self.date_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.date_btn.setObjectName("DateBtn")
        self.date_btn.clicked.connect(self.show_date_picker)
        self.add_btn = QPushButton("+", parent=capsule)
        self.add_btn.setFixedSize(28, 28)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.add_btn.setObjectName("AddBtn")
        self.add_btn.clicked.connect(self.add_task_handler)
        capsule_layout.addWidget(self.flag_btn)
        capsule_layout.addWidget(self.input_line)
        capsule_layout.addWidget(self.lbl_deadline_preview)
        capsule_layout.addWidget(self.repeat_btn)
        capsule_layout.addWidget(self.date_btn)
        capsule_layout.addWidget(self.add_btn)
        layout.addWidget(capsule)
        self.container_layout.addWidget(self.input_frame)

    def set_recurrence(self, value, name):
        self.selected_recurrence = value
        if value:
            self.repeat_btn.setStyleSheet("QPushButton { color: #4CAF50; border: none; font-weight: bold; border-radius: 4px; padding: 0px; text-align: center; } QPushButton::menu-indicator { width: 0px; image: none; }")
            self.repeat_btn.setToolTip(f"重复: {name}")
        else:
            self.repeat_btn.setStyleSheet("QPushButton { border: none; color: #888; border-radius: 4px; padding: 0px; text-align: center; } QPushButton:hover { color: white; background: rgba(255,255,255,0.1); } QPushButton::menu-indicator { width: 0px; image: none; }")
            self.repeat_btn.setToolTip("设置重复")

    def toggle_settings(self):
        self.is_settings_visible = not self.is_settings_visible
        self.settings_panel.setVisible(self.is_settings_visible)

    def change_opacity(self, value):
        self.opacity_val = value
        self.apply_styles()

    def change_bg_color(self, rgb_str):
        self.bg_color_rgb = rgb_str
        self.apply_styles()

    def pick_custom_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color_rgb = f"{color.red()}, {color.green()}, {color.blue()}"
            self.apply_styles()

    def show_date_picker(self):
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        dialog.setStyleSheet("background: #2b2b2b; border: 1px solid #444; border-radius: 8px;")
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(5,5,5,5)
        cal = QCalendarWidget()
        cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        cal.setStyleSheet("QCalendarWidget QWidget { color: #ddd; alternate-background-color: #333; } QAbstractItemView:enabled { color: white; background: #2b2b2b; selection-background-color: #4CAF50; border-radius: 4px;} QMenu { color: white; background: #333; } QSpinBox { color: white; background: #444; border-radius: 4px; } QToolButton { color: white; background: transparent; icon-size: 16px; outline: none; } QToolButton:hover { background: #444; border-radius: 4px; }")
        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH:mm")
        time_edit.setTime(QDateTime.currentDateTime().time())
        time_edit.setStyleSheet("color: white; background: #444; border: none; padding: 4px; border-radius: 4px;")
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        ok_btn.setStyleSheet("background: #4CAF50; color: white; border: none; padding: 6px; border-radius: 4px; font-weight: bold;")
        clear_btn = QPushButton("清除")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        clear_btn.setStyleSheet("background: #555; color: white; border: none; padding: 6px; border-radius: 4px;")
        ok_btn.clicked.connect(dialog.accept)
        clear_btn.clicked.connect(lambda: dialog.done(2))
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(ok_btn)
        layout.addWidget(cal)
        layout.addWidget(time_edit)
        layout.addLayout(btn_layout)
        screen_geo = self.screen().availableGeometry()
        cursor_pos = QCursor.pos()
        dialog_w, dialog_h = 260, 260
        x = cursor_pos.x()
        y = cursor_pos.y()
        if x + dialog_w > screen_geo.right(): x = screen_geo.right() - dialog_w - 10
        if y + dialog_h > screen_geo.bottom(): y = screen_geo.bottom() - dialog_h - 10
        dialog.move(x, y)
        res = dialog.exec()
        if res == 1:
            date = cal.selectedDate()
            time = time_edit.time()
            dt = QDateTime(date, time)
            self.selected_deadline = dt.toString("yyyy-MM-dd HH:mm")
            self.lbl_deadline_preview.setText(dt.toString("MM-dd HH:mm"))
            self.date_btn.setProperty("has_date", "true")
            self.date_btn.setToolTip(f"已选: {self.selected_deadline}")
        elif res == 2:
            self.selected_deadline = ""
            self.lbl_deadline_preview.setText("")
            self.date_btn.setProperty("has_date", "false")
            self.date_btn.setToolTip("设置截止时间")
        self.date_btn.style().unpolish(self.date_btn)
        self.date_btn.style().polish(self.date_btn)

    def add_task_handler(self):
        text = self.input_line.text().strip()
        if not text: return
        priority = self.flag_btn.current_priority
        self.db.add_task(text, priority, self.selected_deadline, self.selected_recurrence)
        self.input_line.clear()
        self.selected_deadline = ""
        self.selected_recurrence = None
        self.lbl_deadline_preview.setText("")
        self.date_btn.setProperty("has_date", "false")
        self.date_btn.style().unpolish(self.date_btn)
        self.date_btn.style().polish(self.date_btn)
        self.repeat_btn.setStyleSheet("QPushButton { border: none; color: #888; border-radius: 4px; padding: 0px; text-align: center; } QPushButton:hover { color: white; background: rgba(255,255,255,0.1); } QPushButton::menu-indicator { width: 0px; image: none; }")
        self.load_tasks()

    def toggle_mode(self):
        self.is_mini_mode = not self.is_mini_mode
        self.scroll_area.setVisible(not self.is_mini_mode)
        if not self.is_locked: self.input_frame.setVisible(not self.is_mini_mode)
        if self.is_mini_mode: self.settings_panel.setVisible(False)
        self.mini_widget.setVisible(self.is_mini_mode)
        if self.is_mini_mode:
            self.saved_height = self.height()
            self.resize(self.width(), 100)
            self.load_tasks()
        else:
            h = getattr(self, 'saved_height', 650)
            self.resize(self.width(), h)

    def apply_styles(self):
        self.setStyleSheet(f"""
            #Container {{ background-color: rgba({self.bg_color_rgb}, {self.opacity_val}); border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.08); }}
            #TitleBtn {{ background: transparent; border-radius: 5px; color: rgba(255,255,255,0.6); font-size: 14px; outline: none; }}
            #TitleBtn:hover {{ background: rgba(255,255,255,0.1); color: white; }}
            #CloseBtn {{ background: transparent; border-radius: 5px; color: rgba(255,255,255,0.6); font-size: 14px; outline: none; }}
            #CloseBtn:hover {{ background: #FF5252; color: white; }}
            #InputCapsule {{ background-color: rgba(0, 0, 0, 0.25); border-radius: 20px; border: 1px solid rgba(255,255,255,8); }}
            #AddBtn {{ background-color: rgba(255,255,255,0.9); color: black; border-radius: 14px; font-weight: bold; font-size: 16px; outline: none; }}
            #AddBtn:hover {{ background-color: white; }}
            #DateBtn {{ background: transparent; border: none; font-size: 16px; color: #888; outline: none; }}
            #DateBtn:hover {{ color: white; }}
            #DateBtn[has_date="true"] {{ color: #4CAF50; }}
            #TaskRow {{ background-color: rgba(255, 255, 255, 0.04); border-radius: 12px; border: 1px solid rgba(255,255,255,5); }}
            #TaskRow:hover {{ background-color: rgba(255, 255, 255, 0.08); }}
            #DeleteBtn {{ color: #666; background: transparent; border: none; font-weight: bold; font-size: 14px; outline: none; }}
            #DeleteBtn:hover {{ color: #FF5252; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.15); border-radius: 3px; }}
            QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.25); }}
        """)

    def update_mini_display(self, task):
        if task:
            self.current_mini_task_id = task[0]
            self.mini_label.setText(task[1])
            self.mini_check.setChecked(False)
            self.mini_check.priority = task[3]
            self.mini_check.update()
            self.mini_check.setEnabled(True)
        else:
            self.current_mini_task_id = None
            self.mini_label.setText("所有任务已完成")
            self.mini_label.setStyleSheet("color: #4CAF50;")
            self.mini_check.setChecked(True)
            self.mini_check.priority = 1
            self.mini_check.update()
            self.mini_check.setEnabled(False)

    def complete_mini_task(self):
        if self.mini_check.isChecked() and self.current_mini_task_id:
            QTimer.singleShot(300, lambda: self.on_status_change(self.current_mini_task_id, True))

    def on_delete(self, t_id):
        self.db.delete_task(t_id)
        self.load_tasks()

    def resizeEvent(self, event):
        if hasattr(self, 'size_grip'):
            x = self.width() - self.SHADOW_WIDTH_PX - 20
            y = self.height() - self.SHADOW_WIDTH_PX - 20
            self.size_grip.move(x, y)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if self.is_locked: return
        if event.button() == Qt.MouseButton.LeftButton and self.container.underMouse():
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.is_locked: return
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, 'drag_pos'):
            target_pos = event.globalPosition().toPoint() - self.drag_pos
            screen = self.screen().availableGeometry()
            w, h = self.width(), self.height()
            min_x = screen.left() - self.SHADOW_WIDTH_PX
            max_x = screen.right() - (w - self.SHADOW_WIDTH_PX)
            min_y = screen.top() - self.SHADOW_WIDTH_PX
            max_y = screen.bottom() - (h - self.SHADOW_WIDTH_PX)
            x = max(min_x, min(target_pos.x(), max_x))
            y = max(min_y, min(target_pos.y(), max_y))
            self.move(x, y)
            event.accept()

    def reset_close_preference(self):
        self.db.set_setting("close_action", "")
        self.btn_reset_close.setText("已重置 ✓")
        QTimer.singleShot(1500, lambda: self.btn_reset_close.setText("重置关闭选项"))

    def closeEvent(self, event):
        """ 重写关闭事件：检查用户偏好，决定是退出还是最小化 """
        
        # 读取数据库中的设置
        action = self.db.get_setting("close_action")
        
        if action == "minimize":
            event.ignore() # 忽略原生关闭
            self.hide()
            self.tray_icon.showMessage("Todo", "已最小化到托盘", QSystemTrayIcon.MessageIcon.NoIcon, 1000)
            return
            
        elif action == "exit":
            # 正常退出
            event.accept()
            QApplication.instance().quit()
            return
            
        # 如果没有保存过设置，弹出询问框
        dialog = CloseDialog(self)
        if dialog.exec():
            choice = dialog.choice
            if dialog.remember:
                self.db.set_setting("close_action", choice)
            
            if choice == "minimize":
                event.ignore()
                self.hide()
            else:
                event.accept()
                QApplication.instance().quit()
        else:
            # 用户取消或关闭了弹窗，取消关闭操作
            event.ignore()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TodoAppV20()
    window.show()
    sys.exit(app.exec())