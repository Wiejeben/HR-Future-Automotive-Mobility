from threading import Thread
from lib.constants import *
import os
import socket
import time
import select

# noinspection PyUnresolvedReferences
from lib import settings


class SocketClient:
    def __init__(self, identity: str, on_disconnect=None):
        self.host = str(os.getenv('SOCKET_HOST', '0.0.0.0'))
        self.port = int(os.getenv('SOCKET_PORT'))
        self.connection = None
        self.on_disconnect = on_disconnect
        self.identity = identity
        self.connected = False

    def connect(self, times_retrying: int = 20) -> bool:
        print('Connecting to remote host', self.host + ':' + str(self.port))

        try:
            self.connection = socket.socket()
            self.connection.connect((self.host, self.port))
            self.send_command(self.identity)

            if not self.receive() == SOCKET_ID_APPROVED:
                print('raised exception')
                raise Exception('Unknown identity ' + self.identity)

            self.connected = True
        except socket.error as exception:
            print('Failed to connect to server:', exception)

            if times_retrying > 0:
                print('Retrying in 2 seconds (' + str(times_retrying - 1) + ' attempts left)')
                time.sleep(2)
                return self.connect(times_retrying - 1)

            return False

        print('Connection established')
        self.connected = True
        return True

    def disconnect(self) -> None:
        print('Closing connection')

        if self.on_disconnect:
            self.on_disconnect()

        # 0 = done receiving, 1 = done sending, 2 = both
        self.connection.close()
        self.connected = False

    def listen(self, callback, reconnect=True) -> None:
        print('Started listening')
        try:
            while True:
                try:
                    # Use select so that as soon as the connection fails, we will be able to reconnect
                    ready_to_read, ready_to_write, in_error = select.select(
                        [self.connection, ], [self.connection, ], [], 5
                    )

                    if len(ready_to_read) > 0:
                        recv = self.receive()

                        if not recv:
                            print('Server left the room')
                            self.disconnect()

                            if not reconnect:
                                break

                            if not self.connect():
                                break

                            continue

                        messages = recv.strip(SOCKET_EOL).split(SOCKET_EOL)
                        for message in messages:
                            callback(message)

                except select.error as exception:
                    print('Connection error:', exception)
                    self.connected = False

                    if not reconnect:
                        break

                    if not self.connect():
                        break

                time.sleep(0.1)
        except KeyboardInterrupt:
            self.disconnect()

    def receive(self):
        return self.connection.recv(1024).decode()

    def send(self, message: str) -> bool:
        try:
            self.connection.send((message + SOCKET_EOL).encode())
            return True
        except:
            return False

    def send_command(self, command: str, *params) -> bool:
        payload = ' '.join([command] + [str(i) for i in list(params)])
        return self.send(payload)


if __name__ == '__main__':
    def on_disconnect() -> None:
        print('Server disconnected')


    def on_message(message: str) -> None:
        print('Received:', message)


    def communicate(client: SocketClient) -> None:
        while True:
            client.send(input())


    print('Enter identity:')
    client = SocketClient('id_' + input(), on_disconnect)

    if client.connect():
        Thread(target=communicate, args=(client,), daemon=True).start()
        client.listen(on_message)
