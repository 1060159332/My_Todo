import sys
import sqlite3
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QScrollArea, 
                             QLabel, QFrame, QCheckBox, QSlider, QGraphicsDropShadowEffect, 
                             QCalendarWidget, QSizeGrip, QDialog, QTimeEdit, QColorDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QDateTime, QPoint, QTimer, QSize, QRect, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QCursor

# ==========================================
# 1. 数据库管理模块 (Database Manager)
# ==========================================
class DatabaseManager:
    """处理所有SQLite数据库操作"""
    def __init__(self, db_name="todo_final.db"):
        self.db_name = db_name
        self.init_db()

    def init_db(self):
        """初始化数据库表结构"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # 创建任务表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                is_done INTEGER DEFAULT 0,
                priority INTEGER DEFAULT 1,
                deadline TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 自动迁移检查：确保旧数据库也有新字段
        cursor.execute("PRAGMA table_info(tasks)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'priority' not in columns: cursor.execute("ALTER TABLE tasks ADD COLUMN priority INTEGER DEFAULT 1")
        if 'deadline' not in columns: cursor.execute("ALTER TABLE tasks ADD COLUMN deadline TEXT")
        
        conn.commit()
        conn.close()

    def add_task(self, content, priority, deadline_str):
        """添加新任务"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO tasks (content, priority, deadline, is_done) VALUES (?, ?, ?, 0)', 
                       (content, priority, deadline_str))
        conn.commit()
        conn.close()

    def get_tasks(self):
        """获取所有任务，按特定逻辑排序"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        # 排序逻辑：未完成优先 > 优先级高优先 > 有截止时间优先 > 截止时间早优先 > 后创建的优先
        cursor.execute('''
            SELECT id, content, is_done, priority, deadline 
            FROM tasks 
            ORDER BY is_done ASC, priority DESC, 
                     CASE WHEN deadline = '' THEN 1 ELSE 0 END, 
                     deadline ASC, id DESC
        ''')
        tasks = cursor.fetchall()
        conn.close()
        return tasks

    def update_status(self, task_id, is_done):
        """更新任务完成状态"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET is_done = ? WHERE id = ?', (1 if is_done else 0, task_id))
        conn.commit()
        conn.close()

    def delete_task(self, task_id):
        """删除任务"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()

# ==========================================
# 2. 自定义 UI 组件 (Custom UI Components)
# ==========================================

class CompleteBtn(QPushButton):
    """ 
    自定义完成按钮（仿苹果 Reminders 的圆圈）
    替代原生 CheckBox，彻底解决样式丑和可能存在的系统弹窗干扰
    """
    def __init__(self, is_done=False, priority=1, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setChecked(is_done)
        # 关键修复：禁用焦点，防止点击时出现虚线框（被用户误认为是弹窗）
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.priority = priority
        # 优先级颜色配置
        self.colors = {1: "#9E9E9E", 2: "#FFC107", 3: "#FF5252"} 

    def paintEvent(self, event):
        """ 自定义绘制圆圈和勾号 """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 将矩形转换为浮点数矩形，修复 TypeError
        rect_int = self.rect().adjusted(2, 2, -2, -2)
        rect = QRectF(rect_int) 
        
        path = QPainterPath()
        path.addEllipse(rect)
        
        # 获取当前优先级对应的颜色
        p_color = QColor(self.colors.get(self.priority, "#9E9E9E"))
        
        if self.isChecked():
            # 状态：已完成 (实心圆 + 勾)
            painter.fillPath(path, p_color)
            painter.setPen(Qt.PenStyle.NoPen)
            
            # 绘制白色的勾
            pen = QPen(Qt.GlobalColor.white)
            pen.setWidthF(2.0)
            painter.setPen(pen)
            
            center = rect.center()
            # 勾的三个点坐标
            p1 = QPoint(int(center.x() - 4), int(center.y()))
            p2 = QPoint(int(center.x() - 1), int(center.y() + 3))
            p3 = QPoint(int(center.x() + 4), int(center.y() - 3))
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
        else:
            # 状态：未完成 (空心圆环)
            pen = QPen(p_color)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

class PriorityButton(QPushButton):
    """ 优先级切换旗帜按钮 """
    priority_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 禁用焦点框
        self.current_priority = 1 
        self.colors = {1: "#4CAF50", 2: "#FFC107", 3: "#F44336"}
        self.clicked.connect(self.cycle_priority)
        self.update_style()

    def cycle_priority(self):
        """ 点击循环切换优先级 (1->2->3->1) """
        self.current_priority = (self.current_priority % 3) + 1
        self.update_style()
        self.priority_changed.emit(self.current_priority)

    def update_style(self):
        color = self.colors[self.current_priority]
        self.setText("⚑")
        self.setStyleSheet(f"""
            QPushButton {{
                color: {color}; background: transparent; border: none;
                font-size: 18px; font-weight: bold;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,0.08); border-radius: 15px; }}
        """)

class TaskWidget(QFrame):
    """ 单个任务条目组件 """
    delete_requested = pyqtSignal(int)
    status_changed = pyqtSignal(int, bool)

    def __init__(self, t_id, content, is_done, priority, deadline, parent=None):
        super().__init__(parent)
        self.t_id = t_id
        self.content = content
        self.is_done = bool(is_done)
        self.priority = priority
        self.deadline = deadline
        self.init_ui()

    def init_ui(self):
        self.setObjectName("TaskRow")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)
        
        # 1. 完成按钮 (使用自定义 CompleteBtn)
        self.check_btn = CompleteBtn(self.is_done, self.priority)
        self.check_btn.clicked.connect(self.on_check)
        
        # 2. 内容区域 (文本 + 时间)
        content_layout = QVBoxLayout()
        content_layout.setSpacing(3)
        
        self.lbl_content = QLabel(self.content)
        self.lbl_content.setWordWrap(True)
        # 优化字体显示
        self.lbl_content.setStyleSheet("font-size: 13px; color: rgba(255,255,255,0.9); font-family: 'Segoe UI', sans-serif;")
        
        self.lbl_time = QLabel()
        self.update_time_label()
        
        content_layout.addWidget(self.lbl_content)
        content_layout.addWidget(self.lbl_time)
        
        # 3. 删除按钮
        self.del_btn = QPushButton("✕")
        self.del_btn.setFixedSize(24, 24)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 禁用焦点框
        self.del_btn.setObjectName("DeleteBtn")
        self.del_btn.clicked.connect(lambda: self.delete_requested.emit(self.t_id))

        layout.addWidget(self.check_btn)
        layout.addLayout(content_layout, 1)
        layout.addWidget(self.del_btn)
        
        self.update_visual_state()

    def update_time_label(self):
        """ 根据截止时间更新显示文本和颜色 """
        if not self.deadline:
            self.lbl_time.hide()
            return
        
        self.lbl_time.show()
        try:
            dt_dead = datetime.strptime(self.deadline, "%Y-%m-%d %H:%M")
            dt_now = datetime.now()
            
            if self.is_done:
                self.lbl_time.setText(f"{dt_dead.strftime('%m-%d')}")
                self.lbl_time.setStyleSheet("color: rgba(255,255,255,0.2); font-size: 10px;")
            else:
                delta = dt_dead - dt_now
                # 逻辑：过期变红，今天变黄，其他变灰
                if delta.total_seconds() < 0:
                    self.lbl_time.setText(f"已过期 {dt_dead.strftime('%m-%d %H:%M')}")
                    self.lbl_time.setStyleSheet("color: #FF5252; font-weight: 600; font-size: 10px;")
                elif delta.days == 0:
                    hrs = int(delta.seconds / 3600)
                    mins = int((delta.seconds % 3600) / 60)
                    self.lbl_time.setText(f"剩余 {hrs}小时{mins}分")
                    self.lbl_time.setStyleSheet("color: #FFC107; font-size: 10px;")
                else:
                    self.lbl_time.setText(f"{dt_dead.strftime('%m-%d %H:%M')} 截止")
                    self.lbl_time.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px;")
        except:
            self.lbl_time.hide()

    def on_check(self):
        """ 处理完成点击事件 """
        self.is_done = self.check_btn.isChecked()
        self.update_visual_state()
        # 发送信号，不弹窗
        self.status_changed.emit(self.t_id, self.is_done)

    def update_visual_state(self):
        """ 更新删除线和透明度 """
        font = self.lbl_content.font()
        font.setStrikeOut(self.is_done)
        self.lbl_content.setFont(font)
        
        if self.is_done:
            self.lbl_content.setStyleSheet("color: rgba(255,255,255,0.3);")
        else:
            self.lbl_content.setStyleSheet("color: rgba(255,255,255,0.9);")
        self.update_time_label()

# ==========================================
# 3. 主窗口 (Main Window)
# ==========================================
class TodoAppPerfect(QMainWindow):
    # 定义阴影宽度 (用于计算边缘吸附)
    SHADOW_WIDTH = 25 

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.is_mini_mode = False
        self.is_locked = False
        self.is_settings_visible = False
        self.selected_deadline = ""
        
        # 默认外观设置
        self.bg_color_rgb = "30, 30, 35"
        self.opacity_val = 240
        
        self.init_ui()
        self.load_tasks()

    def init_ui(self):
        self.resize(390, 600)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 1. 阴影特效 (Shadow Effect) - 优化：更大更柔和
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(45) # 增加模糊半径，更柔和
        self.shadow.setXOffset(0)
        self.shadow.setYOffset(0)     # 居中阴影
        self.shadow.setColor(QColor(0, 0, 0, 120)) # 稍微加深阴影

        # 2. 主窗口部件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        self.main_layout = QVBoxLayout(self.central_widget)
        # 关键：设置 Margin 以容纳阴影，避免阴影被切断
        self.main_layout.setContentsMargins(self.SHADOW_WIDTH, self.SHADOW_WIDTH, self.SHADOW_WIDTH, self.SHADOW_WIDTH)
        
        # 3. 核心容器 (Container) - 实际可见的窗口部分
        self.container = QFrame()
        self.container.setObjectName("Container")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(0)
        self.container.setGraphicsEffect(self.shadow)
        
        self.main_layout.addWidget(self.container)

        # 加载各部分UI
        self.setup_title_bar()
        self.setup_settings_panel()
        self.setup_mini_mode()
        self.setup_task_list()
        self.setup_input_area()

        # 4. 调整大小手柄 (Size Grip)
        self.size_grip = QSizeGrip(self)
        self.size_grip.setFixedSize(20, 20)
        self.size_grip.setStyleSheet("background: transparent;")
        self.size_grip.raise_() # 确保在最上层

        self.apply_styles()

    def setup_title_bar(self):
        """ 顶部标题栏 """
        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(46)
        layout = QHBoxLayout(self.title_bar)
        layout.setContentsMargins(16, 0, 12, 0)

        self.title_label = QLabel("ToDo")
        self.title_label.setStyleSheet("color: rgba(255,255,255,0.95); font-weight: 700; font-size: 15px;")

        # 右侧功能按钮
        self.pin_btn = self.create_title_btn("📌", "置顶窗口")
        self.pin_btn.clicked.connect(self.toggle_top_most)
        
        self.lock_btn = self.create_title_btn("🔓", "锁定交互")
        self.lock_btn.clicked.connect(self.toggle_lock)
        
        self.settings_btn = self.create_title_btn("⚙", "设置")
        self.settings_btn.clicked.connect(self.toggle_settings)
        
        self.mode_btn = self.create_title_btn("⛶", "极简模式")
        self.mode_btn.clicked.connect(self.toggle_mode)
        
        self.btn_min = self.create_title_btn("－", "最小化")
        self.btn_min.clicked.connect(self.showMinimized)
        
        self.btn_close = self.create_title_btn("✕", "关闭")
        self.btn_close.clicked.connect(self.close)
        self.btn_close.setObjectName("CloseBtn") # 使用独立样式

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
        """ 辅助函数：创建标题栏按钮 """
        btn = QPushButton(text)
        btn.setFixedSize(30, 30)
        btn.setCheckable(True) if text in ["📌", "🔓"] else None
        btn.setToolTip(tooltip)
        btn.setObjectName("TitleBtn")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 关键：禁用焦点框
        return btn

    def setup_settings_panel(self):
        """ 设置面板：颜色和透明度 """
        self.settings_panel = QFrame()
        self.settings_panel.setVisible(False)
        self.settings_panel.setStyleSheet("background-color: rgba(0,0,0,0.15); border-bottom: 1px solid rgba(255,255,255,0.05);")
        
        layout = QVBoxLayout(self.settings_panel)
        layout.setContentsMargins(20, 15, 20, 15)

        # 透明度滑块
        h_op = QHBoxLayout()
        lbl_op = QLabel("透明度")
        lbl_op.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(50, 255)
        self.opacity_slider.setValue(240)
        self.opacity_slider.valueChanged.connect(self.change_opacity)
        h_op.addWidget(lbl_op)
        h_op.addWidget(self.opacity_slider)

        # 颜色选择
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

        layout.addLayout(h_op)
        layout.addLayout(h_col)
        self.container_layout.addWidget(self.settings_panel)

    def create_color_btn(self, rgb, hex_code):
        btn = QPushButton()
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setStyleSheet(f"background-color: {hex_code}; border: 1.5px solid rgba(255,255,255,0.3); border-radius: 11px;")
        btn.clicked.connect(lambda: self.change_bg_color(rgb))
        return btn

    def setup_mini_mode(self):
        """ 极简模式布局 """
        self.mini_widget = QFrame()
        self.mini_widget.setVisible(False)
        self.mini_widget.setFixedHeight(50)
        layout = QHBoxLayout(self.mini_widget)
        layout.setContentsMargins(20, 0, 20, 0)
        
        self.mini_check = CompleteBtn()
        self.mini_check.clicked.connect(self.complete_mini_task)
        
        self.mini_label = QLabel("暂无任务")
        self.mini_label.setStyleSheet("color: white; font-size: 14px; font-weight: 500;")
        
        layout.addWidget(self.mini_check)
        layout.addWidget(self.mini_label, 1)
        self.container_layout.addWidget(self.mini_widget)

    def setup_task_list(self):
        """ 任务列表区域 """
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")
        # 禁用滚动条焦点
        self.scroll_area.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        
        self.tasks_container = QWidget()
        self.tasks_container.setStyleSheet("background: transparent;")
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setContentsMargins(8, 8, 8, 8)
        self.tasks_layout.setSpacing(6)
        self.tasks_layout.addStretch()
        
        self.scroll_area.setWidget(self.tasks_container)
        self.container_layout.addWidget(self.scroll_area)

    def setup_input_area(self):
        """ 底部输入区域 """
        self.input_frame = QFrame()
        self.input_frame.setFixedHeight(70)
        self.input_frame.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self.input_frame)
        layout.setContentsMargins(16, 5, 16, 20)
        
        capsule = QFrame()
        capsule.setObjectName("InputCapsule")
        capsule_layout = QHBoxLayout(capsule)
        capsule_layout.setContentsMargins(8, 4, 8, 4)
        
        self.flag_btn = PriorityButton()
        
        self.input_line = QLineEdit()
        self.input_line.setPlaceholderText("添加新任务...")
        self.input_line.setStyleSheet("border: none; color: white; background: transparent; font-size: 13px;")
        self.input_line.returnPressed.connect(self.add_task_handler)
        
        self.lbl_deadline_preview = QLabel("")
        self.lbl_deadline_preview.setStyleSheet("color: #4CAF50; font-size: 11px; margin-right: 6px; font-weight: bold;")
        
        self.date_btn = QPushButton("⏰")
        self.date_btn.setFixedSize(28, 28)
        self.date_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.date_btn.setObjectName("DateBtn")
        self.date_btn.clicked.connect(self.show_date_picker)
        self.date_btn.setToolTip("设置截止时间")
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(28, 28)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.add_btn.setObjectName("AddBtn")
        self.add_btn.clicked.connect(self.add_task_handler)

        capsule_layout.addWidget(self.flag_btn)
        capsule_layout.addWidget(self.input_line)
        capsule_layout.addWidget(self.lbl_deadline_preview)
        capsule_layout.addWidget(self.date_btn)
        capsule_layout.addWidget(self.add_btn)
        
        layout.addWidget(capsule)
        self.container_layout.addWidget(self.input_frame)

    # --- 逻辑功能 (Logic) ---

    def show_date_picker(self):
        """ 显示日期选择对话框 """
        dialog = QDialog(self)
        dialog.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        dialog.setStyleSheet("background: #2b2b2b; border: 1px solid #444; border-radius: 8px;")
        
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(5,5,5,5)
        
        cal = QCalendarWidget()
        cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        cal.setStyleSheet("""
            QCalendarWidget QWidget { color: #ddd; alternate-background-color: #333; }
            QAbstractItemView:enabled { color: white; background: #2b2b2b; selection-background-color: #4CAF50; border-radius: 4px;}
            QMenu { color: white; background: #333; }
            QSpinBox { color: white; background: #444; border-radius: 4px; }
            QToolButton { color: white; background: transparent; icon-size: 16px; }
            QToolButton:hover { background: #444; border-radius: 4px; }
        """)
        
        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH:mm")
        time_edit.setTime(QDateTime.currentDateTime().time())
        time_edit.setStyleSheet("color: white; background: #444; border: none; padding: 4px; border-radius: 4px;")
        
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet("background: #4CAF50; color: white; border: none; padding: 6px; border-radius: 4px; font-weight: bold;")
        clear_btn = QPushButton("清除")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setStyleSheet("background: #555; color: white; border: none; padding: 6px; border-radius: 4px;")
        
        ok_btn.clicked.connect(dialog.accept)
        clear_btn.clicked.connect(lambda: dialog.done(2))
        
        btn_layout.addWidget(clear_btn)
        btn_layout.addWidget(ok_btn)
        
        layout.addWidget(cal)
        layout.addWidget(time_edit)
        layout.addLayout(btn_layout)
        
        # 智能定位：防止对话框超出屏幕
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
        """ 处理添加任务 """
        text = self.input_line.text().strip()
        if not text: return
        
        priority = self.flag_btn.current_priority
        self.db.add_task(text, priority, self.selected_deadline)
        
        # 重置输入状态
        self.input_line.clear()
        self.selected_deadline = ""
        self.lbl_deadline_preview.setText("")
        self.date_btn.setProperty("has_date", "false")
        self.date_btn.style().unpolish(self.date_btn)
        self.date_btn.style().polish(self.date_btn)
        self.load_tasks()

    def toggle_top_most(self):
        """ 切换窗口置顶 """
        pos = self.pos()
        self.is_top_most = self.pin_btn.isChecked()
        flags = self.windowFlags()
        if self.is_top_most:
            flags |= Qt.WindowType.WindowStaysOnTopHint
            self.pin_btn.setStyleSheet("background-color: rgba(76, 175, 80, 0.3); border: 1px solid rgba(76,175,80,0.5);")
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
            self.pin_btn.setStyleSheet("")
        
        self.setWindowFlags(flags)
        self.move(pos)
        self.show()

    def toggle_lock(self):
        """ 切换锁定模式（防误触） """
        self.is_locked = self.lock_btn.isChecked()
        if self.is_locked:
            self.lock_btn.setText("🔒")
            self.lock_btn.setStyleSheet("background-color: rgba(244, 67, 54, 0.3); border: 1px solid rgba(244,67,54,0.5);")
            self.title_label.setText("ToDo (Locked)")
            
            self.input_frame.hide()
            self.settings_panel.setVisible(False)
            self.settings_btn.setVisible(False)
            self.pin_btn.setVisible(False)
            self.mode_btn.setVisible(False)
            self.btn_min.setVisible(False)
            self.btn_close.setVisible(False)
            self.size_grip.setVisible(False)
            
            # 设置内容区域对鼠标透明（不可点击）
            self.scroll_area.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.mini_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.lock_btn.setText("🔓")
            self.lock_btn.setStyleSheet("")
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

    def toggle_settings(self):
        self.is_settings_visible = not self.is_settings_visible
        self.settings_panel.setVisible(self.is_settings_visible)

    def toggle_mode(self):
        """ 切换 完整/极简 模式 """
        self.is_mini_mode = not self.is_mini_mode
        self.scroll_area.setVisible(not self.is_mini_mode)
        
        if not self.is_locked:
            self.input_frame.setVisible(not self.is_mini_mode)
        if self.is_mini_mode: self.settings_panel.setVisible(False)
        
        self.mini_widget.setVisible(self.is_mini_mode)
        
        if self.is_mini_mode:
            self.saved_height = self.height()
            self.resize(self.width(), 100)
            self.update_mini_display(None)
            self.load_tasks()
        else:
            h = getattr(self, 'saved_height', 600)
            self.resize(self.width(), h)

    def apply_styles(self):
        """ 
        应用样式表 
        优化点：边框颜色极淡 (rgba 255,255,255,0.08) 以实现完美过渡
        """
        self.setStyleSheet(f"""
            #Container {{
                background-color: rgba({self.bg_color_rgb}, {self.opacity_val});
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.08); /* 极淡边框 */
            }}
            #TitleBtn {{ background: transparent; border-radius: 5px; color: rgba(255,255,255,0.6); font-size: 14px; outline: none; }}
            #TitleBtn:hover {{ background: rgba(255,255,255,0.1); color: white; }}
            
            #CloseBtn {{ background: transparent; border-radius: 5px; color: rgba(255,255,255,0.6); font-size: 14px; outline: none; }}
            #CloseBtn:hover {{ background: #FF5252; color: white; }}
            
            #InputCapsule {{
                background-color: rgba(0, 0, 0, 0.25);
                border-radius: 20px;
                border: 1px solid rgba(255,255,255,8);
            }}
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

    def load_tasks(self):
        """ 从数据库加载任务到列表 """
        while self.tasks_layout.count() > 1:
            item = self.tasks_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        tasks = self.db.get_tasks()
        first_undone = None
        for task in tasks:
            self.add_task_widget(task)
            if not first_undone and task[2] == 0:
                first_undone = task
        
        self.update_mini_display(first_undone)

    def add_task_widget(self, task_data):
        widget = TaskWidget(*task_data)
        widget.status_changed.connect(self.on_status_change)
        widget.delete_requested.connect(self.on_delete)
        self.tasks_layout.insertWidget(self.tasks_layout.count()-1, widget)

    def update_mini_display(self, task):
        """ 更新极简模式的显示内容 """
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

    def on_status_change(self, t_id, is_done):
        self.db.update_status(t_id, is_done)
        self.load_tasks()

    def on_delete(self, t_id):
        self.db.delete_task(t_id)
        self.load_tasks()

    # --- 窗口事件重写 (Window Events) ---

    def resizeEvent(self, event):
        """ 确保调整大小手柄始终在右下角 """
        if hasattr(self, 'size_grip'):
            # 减去 Margin 以定位在 Container 的右下角
            offset = self.SHADOW_WIDTH + 5
            self.size_grip.move(self.width() - 20 - 5, self.height() - 20 - 5)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if self.is_locked: return
        if event.button() == Qt.MouseButton.LeftButton:
            # 记录点击位置
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        """ 
        处理窗口拖拽 + 边缘吸附修正 
        修复：允许阴影部分移出屏幕，使实体窗口边缘能完美贴合屏幕边缘
        """
        if self.is_locked: return
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, 'drag_pos'):
            target_pos = event.globalPosition().toPoint() - self.drag_pos
            screen = self.screen().availableGeometry()
            w, h = self.width(), self.height()
            
            # 计算边界：允许窗口坐标为负值 (即阴影移出屏幕)，最大值为屏幕尺寸减去窗口实体宽度
            # 实体左边缘贴边 -> x = -SHADOW_WIDTH
            # 实体右边缘贴边 -> x = ScreenWidth - (WindowWidth - SHADOW_WIDTH)
            
            # 左边界
            min_x = screen.left() - self.SHADOW_WIDTH
            # 右边界 (屏幕右边 - 窗口总宽 + 阴影宽)
            max_x = screen.right() - w + self.SHADOW_WIDTH
            
            # 上边界
            min_y = screen.top() - self.SHADOW_WIDTH
            # 下边界
            max_y = screen.bottom() - h + self.SHADOW_WIDTH
            
            # 限制坐标
            x = max(min_x, min(target_pos.x(), max_x))
            y = max(min_y, min(target_pos.y(), max_y))
            
            self.move(x, y)
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TodoAppPerfect()
    window.show()
    sys.exit(app.exec())