"""
主窗口GUI模块

使用Tkinter实现完整的用户界面，包括配置、控制、进度显示和日志输出。
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import queue
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional
import logging

# 导入模块（支持开发环境和PyInstaller打包）
try:
    # 开发环境 - 使用相对导入
    from ..data.data_manager import Configuration, DataManager, RegistrationTask
    from ..models.account import Account
    from ..utils.logger import default_logger as logger
    from ..engine.flow_engine import FlowLoader, FlowRunner
    from ..browser.provider import BrowserProvider
    from ..utils import config as app_config
except (ImportError, ValueError):
    # PyInstaller打包环境 - 使用绝对导入
    try:
        from src.data.data_manager import Configuration, DataManager, RegistrationTask
        from src.models.account import Account
        from src.utils.logger import default_logger as logger
        from src.engine.flow_engine import FlowLoader, FlowRunner
        from src.browser.provider import BrowserProvider
        from src.utils import config as app_config
    except ImportError:
        # 最后尝试添加路径
        import sys
        import os
        # 添加src目录到Python路径
        src_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        if src_path not in sys.path:
            sys.path.insert(0, src_path)
        
        from src.data.data_manager import Configuration, DataManager, RegistrationTask
        from src.models.account import Account
        from src.utils.logger import default_logger as logger
        from src.engine.flow_engine import FlowLoader, FlowRunner
        from src.browser.provider import BrowserProvider
        from src.utils import config as app_config


class GuiQueueLogHandler(logging.Handler):
    """将日志转发到 GUI 消息队列。"""

    def __init__(self, msg_queue: queue.Queue):
        super().__init__()
        self.msg_queue = msg_queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = record.levelname
            msg = self.format(record)
            self.msg_queue.put({
                "type": "log",
                "message": msg,
                "level": level,
            })
        except Exception:
            pass


class RegistrationWorker(threading.Thread):
    """后台注册工作线程"""
    
    def __init__(
        self,
        task: RegistrationTask,
        config: Configuration,
        data_manager: DataManager,
        message_queue: queue.Queue,
        stop_event: threading.Event,
        manual_continue_event: threading.Event,
        simple_mode: bool = False,
        use_real_profile: bool = False,
        flow_path: Optional[Path] = None,
    ):
        super().__init__(daemon=True)
        self.task = task
        self.config = config
        self.data_manager = data_manager
        self.message_queue = message_queue
        self.stop_event = stop_event
        self.manual_continue_event = manual_continue_event
        self.simple_mode = simple_mode  # True=半自动模式（到人机验证），False=全自动模式
        self.use_real_profile = use_real_profile  # True=使用真实用户配置文件，False=使用临时目录
        self.flow_path: Optional[Path] = flow_path
        self._config_dict = None
        self._flow = None
    
    def run(self):
        """执行注册任务"""
        try:
            self.message_queue.put({
                "type": "status",
                "message": "正在启动浏览器..."
            })

            # 载入全局配置与 Flow（GUI 主入口默认从 config.json 解析 flow.file）
            self._config_dict = app_config.load_config()
            resolved_flow_path = app_config.get_flow_file(self._config_dict, str(self.flow_path) if self.flow_path else None)
            self._flow = FlowLoader.load(resolved_flow_path)

            # 仅半自动模式：不使用邮箱服务
            self._process_accounts(None)
            
        except Exception as e:
            logger.error(f"注册工作线程异常: {e}")
            self.message_queue.put({
                "type": "error",
                "message": f"任务执行失败: {str(e)}"
            })
    
    def _process_accounts(self, email_service):
        """处理账号注册"""
        for account in self.task.accounts:
            # 检查停止标志
            if self.stop_event.is_set():
                self.message_queue.put({
                    "type": "log",
                    "message": "用户停止了注册任务",
                    "level": "WARNING"
                })
                break
            
            # 更新账号状态为进行中
            account.status = "in_progress"
            account.started_at = datetime.now()
            
            self.message_queue.put({
                "type": "status",
                "message": f"正在注册账号 {account.id}/{self.task.statistics.total}"
            })
            
            self.message_queue.put({
                "type": "log",
                "message": f"开始注册账号{account.id}: {account.email}",
                "level": "INFO"
            })
            
            # 定义验证码接收回调
            def on_verification_code(code):
                """验证码接收回调，在GUI中显示"""
                self.message_queue.put({
                    "type": "log",
                    "message": f"📧 收到验证码: {code}",
                    "level": "SUCCESS"
                })
            
            # 为每个账号创建新的浏览器实例
            self.message_queue.put({
                "type": "log",
                "message": f"🌐 启动新的浏览器实例（账号{account.id}）...",
                "level": "INFO"
            })
            
            # 使用配置驱动引擎执行（navigate → ... → pause_for_manual）
            driver = None
            try:
                # headless 配置读取（保持与旧逻辑兼容）
                headless = False
                try:
                    headless = getattr(self.config.registration, 'headless', False)
                except Exception:
                    headless = False

                driver = BrowserProvider.start_browser(headless=headless)

                # 当 Flow 执行到 pause_for_manual（到达人机验证）时，立即标记本账号为 success
                def _mark_reached_manual():
                    try:
                        account.status = "success"
                        account.completed_at = datetime.now()
                        self.task.update_statistics()
                        # 发送进度与日志到 GUI
                        self.message_queue.put({
                            "type": "account_completed",
                            "account_id": account.id,
                            "status": "success"
                        })
                        self.message_queue.put({
                            "type": "progress",
                            "current": self.task.statistics.completed,
                            "total": self.task.statistics.total
                        })
                        self.message_queue.put({
                            "type": "log",
                            "message": f"✅ 账号{account.id}已填写到人机验证（已计入成功）",
                            "level": "INFO"
                        })
                    except Exception as _e:
                        logger.warning(f"标记到达人机验证为成功时出错: {_e}")

                ctx = {
                    "config": self._config_dict or {},
                    "manual_continue_event": self.manual_continue_event,
                    "on_reached_manual": _mark_reached_manual,
                }
                account_ctx = {
                    "email": getattr(account, 'email', None),
                    "password": getattr(account, 'password', None),
                    "first_name": getattr(account, 'first_name', None),
                    "last_name": getattr(account, 'last_name', None),
                }

                # 执行 Flow（停在人机验证由 Flow 的 pause_for_manual 决定）
                FlowRunner.execute(self._flow, driver, account=account_ctx, context=ctx)

                # 设置成功标志（若未在 on_reached_manual 回调中标记成功，则以此为准）
                success = True
                error = None

            except Exception as e:
                success = False
                error = str(e)
            finally:
                # 确保浏览器关闭
                self.message_queue.put({
                    "type": "log",
                    "message": f"🔄 关闭浏览器（账号{account.id}完成）",
                    "level": "INFO"
                })
                try:
                    BrowserProvider.cleanup(driver)
                except Exception:
                    pass
            
            # 更新账号状态（半自动模式下已经标记为success，跳过）
            if account.status != "success":
                account.completed_at = datetime.now()
                if success:
                    account.status = "success"
                    self.message_queue.put({
                        "type": "log",
                        "message": f"账号{account.id}注册成功: {account.email}",
                        "level": "INFO"
                    })
                else:
                    account.status = "failed"
                    account.error_message = error
                    self.message_queue.put({
                        "type": "log",
                        "message": f"账号{account.id}注册失败: {error}",
                        "level": "ERROR"
                    })
            
            # 更新任务统计和发送进度（半自动模式下已发送过，跳过）
            if account.status != "success":
                self.task.update_statistics()
                
                self.message_queue.put({
                    "type": "progress",
                    "current": self.task.statistics.completed,
                    "total": self.task.statistics.total
                })
                
                self.message_queue.put({
                    "type": "account_completed",
                    "account_id": account.id,
                    "status": account.status,
                    "error_message": account.error_message
                })
            
            # 保存任务进度
            try:
                self.data_manager.save_task(self.task)
            except Exception as e:
                logger.warning(f"保存任务进度失败: {e}")
            
            # 间隔时间
            if not self.stop_event.is_set():
                self.stop_event.wait(self.config.registration.interval_seconds)
        
        # 任务完成
        self.message_queue.put({
            "type": "task_completed",
            "statistics": self.task.statistics
        })


class MainWindow:
    """主窗口类"""
    
    def __init__(self, root: tk.Tk, config: Configuration, data_manager: DataManager, existing_task: Optional[RegistrationTask] = None):
        """
        初始化主窗口
        
        Args:
            root: Tkinter根窗口
            config: 应用配置
            data_manager: 数据管理器
            existing_task: 已存在的未完成任务（用于断点续传）
        """
        self.root = root
        self.config = config
        self.data_manager = data_manager
        
        self.message_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.manual_continue_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.current_task: Optional[RegistrationTask] = existing_task
        
        # 将全局日志转发到 GUI 日志面板（仅挂到 root，避免重复）
        try:
            self._gui_log_handler = GuiQueueLogHandler(self.message_queue)
            self._gui_log_handler.setLevel(logging.INFO)
            self._gui_log_handler.setFormatter(logging.Formatter("%(message)s"))
            root_logger = logging.getLogger()
            if not any(isinstance(h, GuiQueueLogHandler) for h in root_logger.handlers):
                root_logger.addHandler(self._gui_log_handler)
        except Exception:
            pass
        
        self._create_ui()
        self._start_queue_check()
        
        # 如果有未完成的任务，提示用户是否继续
        if existing_task:
            self._handle_existing_task(existing_task)
        
        logger.info("MainWindow initialized")
    
    def _create_ui(self):
        """创建UI布局"""
        self.root.title("WindSurf账号批量注册工具")
        self.root.geometry("900x700")
        
        # 配置区域
        config_frame = ttk.LabelFrame(self.root, text="配置", padding=10)
        config_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 注册数量
        ttk.Label(config_frame, text="注册数量:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.count_spinbox = ttk.Spinbox(config_frame, from_=1, to=100, width=10)
        self.count_spinbox.grid(row=1, column=1, sticky=tk.W, pady=2, padx=5)
        self.count_spinbox.set(self.config.registration.default_count)
        
        # 控制按钮区域
        control_frame = ttk.Frame(self.root, padding=10)
        control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.start_button = ttk.Button(
            control_frame,
            text="开始注册",
            command=self.start_registration,
            width=15
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(
            control_frame,
            text="停止",
            command=self.stop_registration,
            state=tk.DISABLED,
            width=15
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.export_button = ttk.Button(
            control_frame,
            text="导出结果",
            command=self.export_results,
            width=15
        )
        self.export_button.pack(side=tk.LEFT, padx=5)
        
        self.manual_continue_button = ttk.Button(
            control_frame,
            text="✓ 手动继续",
            command=self.manual_continue,
            state=tk.DISABLED,
            width=15
        )
        self.manual_continue_button.pack(side=tk.LEFT, padx=5)
        
        # 进度显示区域
        progress_frame = ttk.LabelFrame(self.root, text="进度", padding=10)
        progress_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            length=400
        )
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # 状态标签
        self.status_label = ttk.Label(
            progress_frame,
            text="准备就绪",
            font=("Arial", 10)
        )
        self.status_label.pack(anchor=tk.W, pady=2)
        
        # 统计信息
        stats_frame = ttk.Frame(progress_frame)
        stats_frame.pack(fill=tk.X, pady=2)
        
        self.stats_label = ttk.Label(
            stats_frame,
            text="成功: 0 | 失败: 0 | 总计: 0",
            font=("Arial", 9)
        )
        self.stats_label.pack(anchor=tk.W)
        
        # 日志面板
        log_frame = ttk.LabelFrame(self.root, text="日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # 创建文本框和滚动条
        log_scroll = ttk.Scrollbar(log_frame)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.log_text = tk.Text(
            log_frame,
            height=15,
            wrap=tk.WORD,
            yscrollcommand=log_scroll.set,
            font=("Consolas", 9)
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)
        
        # 配置日志颜色标签
        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("WARNING", foreground="orange")
        self.log_text.tag_config("ERROR", foreground="red")
        
        # 初始日志
        self.log_message("应用程序启动完成", "INFO")
    
    def start_registration(self):
        """开始注册按钮回调"""
        try:
            # 验证输入
            count = int(self.count_spinbox.get())
            if not 1 <= count <= 100:
                messagebox.showerror("错误", "注册数量必须在1-100之间")
                return
            
            # 验证配置
            errors = self.config.validate()
            if errors:
                messagebox.showerror("配置错误", "\n".join(errors))
                return
            
            self.log_message(f"开始生成{count}个账号...", "INFO")
            
            # 生成账号
            accounts = self.data_manager.generate_accounts(count)
            
            # 创建任务
            self.current_task = self.data_manager.create_task(accounts)
            
            self.log_message(f"任务创建成功: {self.current_task.task_id}", "INFO")
            
            # 重置UI状态
            self.progress_var.set(0)
            self.update_stats(0, 0, 0)
            
            # 禁用开始按钮，启用停止按钮和手动继续按钮
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.manual_continue_button.config(state=tk.NORMAL)
            
            # 清除停止标志
            self.stop_event.clear()
            
            # 固定为半自动模式 + 临时目录模式
            is_simple_mode = True
            use_real_profile = False
            self.log_message("使用半自动模式（到人机验证）", "INFO")
            self.log_message("使用临时目录模式", "INFO")
            
            # 启动工作线程
            self.worker_thread = RegistrationWorker(
                self.current_task,
                self.config,
                self.data_manager,
                self.message_queue,
                self.stop_event,
                self.manual_continue_event,
                simple_mode=is_simple_mode,
                use_real_profile=use_real_profile
            )
            self.worker_thread.start()
            
            self.log_message("注册任务已启动", "INFO")
            
        except ValueError as e:
            messagebox.showerror("错误", f"输入无效: {e}")
        except Exception as e:
            logger.error(f"启动注册失败: {e}", exc_info=True)
            messagebox.showerror("错误", f"启动注册失败: {e}")
    
    def stop_registration(self):
        """停止注册按钮回调"""
        if messagebox.askyesno("确认", "确定要停止当前注册任务吗？"):
            self.log_message("正在停止注册任务...", "WARNING")
            
            # 设置停止事件
            self.stop_event.set()
            self.manual_continue_event.set()  # 同时触发手动继续，防止等待
            
            # 禁用停止按钮，防止重复点击
            self.stop_button.config(state=tk.DISABLED)
            
            # 如果有工作线程，强制终止
            if self.worker_thread and self.worker_thread.is_alive():
                self.log_message("正在终止工作线程...", "WARNING")
                # 等待线程自然结束
                self.worker_thread.join(timeout=5)
                if self.worker_thread.is_alive():
                    self.log_message("工作线程未能及时停止，将继续等待", "WARNING")
                else:
                    self.log_message("工作线程已停止", "INFO")
            
            # 更新UI状态
            self.start_button.config(state=tk.NORMAL)
            self.manual_continue_button.config(state=tk.DISABLED)
            self.update_status("任务已停止")
            self.log_message("注册任务已停止", "INFO")
    
    def manual_continue(self):
        """手动继续按钮回调"""
        self.log_message("✓ 用户点击手动继续，进入下一个账号", "INFO")
        self.manual_continue_event.set()
        # 不禁用按钮，允许多次点击
    
    def export_results(self):
        """导出结果按钮回调"""
        if not self.current_task or not self.current_task.accounts:
            messagebox.showwarning("提示", "没有可导出的数据")
            return
        
        # 选择导出文件（默认JSON格式）
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[
                ("JSON文件", "*.json"),
                ("CSV文件", "*.csv"),
                ("所有文件", "*.*")
            ],
            initialfile=f"windsurf-accounts.json"
        )
        
        if file_path:
            try:
                # 导出成功的账号（半自动模式和全自动模式都是success）
                success_accounts = [
                    acc for acc in self.current_task.accounts 
                    if acc.status == "success"
                ]
                
                if not success_accounts:
                    messagebox.showwarning("提示", "没有成功注册的账号可导出")
                    return
                
                # 根据文件扩展名选择导出格式
                file_path_obj = Path(file_path)
                if file_path_obj.suffix.lower() == ".json":
                    self._export_to_json(success_accounts, file_path_obj)
                else:
                    self.data_manager.export_to_csv(success_accounts, file_path_obj)
                
                messagebox.showinfo(
                    "成功",
                    f"成功导出{len(success_accounts)}个账号到:\n{file_path}"
                )
                self.log_message(f"导出成功: {file_path}", "INFO")
                
            except Exception as e:
                logger.error(f"导出失败: {e}", exc_info=True)
                messagebox.showerror("错误", f"导出失败: {e}")
    
    def _export_to_json(self, accounts: list, file_path: Path):
        """导出为JSON格式（简洁格式：只包含email和password）"""
        import json
        
        # 构建简洁的JSON数组
        data = [
            {
                "email": acc.email,
                "password": acc.password
            }
            for acc in accounts
        ]
        
        # 写入JSON文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"导出{len(accounts)}个账号到JSON: {file_path}")
    
    def update_progress(self, current: int, total: int):
        """更新进度条"""
        if total > 0:
            percentage = (current / total) * 100
            self.progress_var.set(percentage)
    
    def update_status(self, message: str):
        """更新状态标签"""
        self.status_label.config(text=message)
    
    def update_stats(self, success: int, failed: int, total: int):
        """更新统计信息"""
        self.stats_label.config(
            text=f"成功: {success} | 失败: {failed} | 总计: {total}"
        )
    
    def log_message(self, message: str, level: str = "INFO"):
        """在日志面板追加消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_line, level)
        self.log_text.see(tk.END)  # 自动滚动到底部
    
    def check_message_queue(self):
        """检查消息队列并更新UI"""
        try:
            while True:
                message = self.message_queue.get_nowait()
                
                msg_type = message.get("type")
                
                if msg_type == "progress":
                    self.update_progress(message["current"], message["total"])
                
                elif msg_type == "status":
                    self.update_status(message["message"])
                
                elif msg_type == "log":
                    self.log_message(message["message"], message.get("level", "INFO"))
                
                elif msg_type == "account_completed":
                    if self.current_task:
                        self.update_stats(
                            self.current_task.statistics.success,
                            self.current_task.statistics.failed,
                            self.current_task.statistics.total
                        )
                
                elif msg_type == "task_completed":
                    stats = message["statistics"]
                    self.log_message(
                        f"任务完成! 成功: {stats.success}, 失败: {stats.failed}",
                        "INFO"
                    )
                    self.update_status("任务已完成")
                    self.start_button.config(state=tk.NORMAL)
                    self.stop_button.config(state=tk.DISABLED)
                    self.manual_continue_button.config(state=tk.DISABLED)
                    
                    messagebox.showinfo(
                        "任务完成",
                        f"注册任务已完成!\n\n"
                        f"总计: {stats.total}\n"
                        f"成功: {stats.success}\n"
                        f"失败: {stats.failed}\n"
                        f"成功率: {stats.success_rate:.1f}%"
                    )
                
                
        except queue.Empty:
            pass
        
        # 每100ms检查一次队列
        self.root.after(100, self.check_message_queue)
    
    def _start_queue_check(self):
        """启动队列检查"""
        self.root.after(100, self.check_message_queue)
    
    def _handle_existing_task(self, task: RegistrationTask):
        """
        处理已存在的未完成任务
        
        Args:
            task: 未完成的任务
        """
        # 弹出提示框询问用户是否继续
        response = messagebox.askyesnocancel(
            "发现未完成的任务",
            f"发现上次未完成的注册任务：\n"
            f"总数：{task.statistics.total}\n"
            f"已完成：{task.statistics.completed}\n"
            f"失败：{task.statistics.failed}\n\n"
            f"是否继续？\n"
            f"（点击'否'将清除此任务）",
            icon='question'
        )
        
        if response is True:
            # 用户选择继续
            logger.info("用户选择继续未完成的任务")
            # 更新UI显示任务信息
            self.count_spinbox.delete(0, tk.END)
            self.count_spinbox.insert(0, str(task.statistics.total - task.statistics.completed - task.statistics.failed))
        elif response is False:
            # 用户选择不继续，清除任务
            logger.info("用户选择清除未完成的任务")
            self.data_manager.clear_task_data()
            self.current_task = None
        else:
            # 用户取消，保留任务但不做任何操作
            logger.info("用户取消操作，保留任务")
