"""极小 single-instance helper：Qt 本地 QLocalServer 守卫（主软件 / UU测算 复用）。

每个应用使用独立 key（UU护航 / UU测算 各一个），同一 key 同时最多一个实例，
不同 key 的实例允许同时各运行一个（UU护航 + UU测算 可并存）。

第二启动实例的行为：
- 不创建第二个窗口、不创建第二个 AppContext；
- 连接既有 server → 发送激活请求 → 进程正常退出；
- 第一个实例收到请求后把主窗口 bring-to-front（show + raise_ + activateWindow）。

不使用后台服务 / daemon / 数据库锁 / 第三方 single-instance 包 / 复杂 IPC 框架；
进程异常退出后的残留由 QLocalServer 自动清理（Windows named pipe 随进程退出
由系统释放，Unix socket 由启动前的 removeServer 清理）。
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

# 两个应用的独立 single-instance key（互不干扰，可同时各运行一个）
UU_ESCORT_INSTANCE_KEY = "profit_accounting_26_uu_escort"
UU_CALCULATOR_INSTANCE_KEY = "profit_accounting_26_uu_calculator"


class SingleInstanceGuard(QObject):
    """单实例守卫：listen 成功 = 本进程为唯一实例；失败 = 已有实例在运行。

    ``already_running`` 为 True 时调用方应直接退出（不构造窗口/AppContext）；
    收到激活请求时发出 ``activateRequested`` 信号。
    """

    activateRequested = Signal()

    def __init__(self, key: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = str(key)
        self._server = QLocalServer(self)
        self._connections: list[QLocalSocket] = []
        self.already_running = self._try_acquire()

    # ------------------------------------------------------------------

    def _try_acquire(self) -> bool:
        """返回 True 表示已有实例在运行（本进程应退出）。"""
        if self._probe_and_activate():
            return True
        # 无实例在运行：清理上次异常退出残留后 listen
        QLocalServer.removeServer(self._key)
        if self._server.listen(self._key):
            self._server.newConnection.connect(self._on_new_connection)
            return False
        # 极端竞态：另一实例刚完成 listen。尝试再次请求激活
        self._probe_and_activate()
        return True

    def _probe_and_activate(self) -> bool:
        """尝试连接既有 server 并请求激活；连接成功返回 True。"""
        socket = QLocalSocket(self)
        socket.connectToServer(self._key)
        if not socket.waitForConnected(500):
            socket.close()
            return False
        socket.write(b"activate")
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.close()
        return True

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            self._connections.append(connection)
            connection.readyRead.connect(
                lambda conn=connection: self._on_ready_read(conn)
            )
            connection.disconnected.connect(
                lambda conn=connection: self._on_disconnected(conn)
            )

    def _on_ready_read(self, connection: QLocalSocket) -> None:
        connection.readAll()
        self.activateRequested.emit()

    def _on_disconnected(self, connection: QLocalSocket) -> None:
        if connection in self._connections:
            self._connections.remove(connection)
        connection.deleteLater()

    # ------------------------------------------------------------------

    def close(self) -> None:
        """显式释放实例锁（测试用；正常退出时进程自动释放）。"""
        if self._server.isListening():
            self._server.close()
        for connection in self._connections:
            connection.close()
        self._connections.clear()
