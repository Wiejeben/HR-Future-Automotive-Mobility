import pygame
from lib.SocketClient import SocketClient
from lib.constants import *
import numpy as np


class Joystick(object):
    def __init__(self):
        pygame.init()
        pygame.joystick.init()
        self.joystick = pygame.joystick.Joystick(0)
        self.joystick.init()

        self.axis_data = None
        self.button_data = None
        self.hat_data = None

        self.client = SocketClient(SOCKET_ID_JOYSTICK)
        self.client.connect()

        self.clock = pygame.time.Clock()

    def send_input(self, message: str):
        """
        Send joystick output to server
        """
        self.client.send(message)

    def listen(self):
        """
        Listen for events from the joystick
        """

        if not self.axis_data:
            self.axis_data = {}

        if not self.button_data:
            self.button_data = {}
            for i in range(self.joystick.get_numbuttons()):
                self.button_data[i] = False

        if not self.hat_data:
            self.hat_data = {}
            for i in range(self.joystick.get_numhats()):
                self.hat_data[i] = (0, 0)

        while True:
            self.clock.tick(10)

            for event in pygame.event.get():
                if event.type == pygame.JOYAXISMOTION:
                    self.axis_data[event.axis] = round(event.value, 2)
                elif event.type == pygame.JOYBUTTONDOWN:
                    self.button_data[event.button] = True
                elif event.type == pygame.JOYBUTTONUP:
                    self.button_data[event.button] = False
                elif event.type == pygame.JOYHATMOTION:
                    self.hat_data[event.hat] = event.value

                # Insert your code on what you would like to happen for each event here!
                # In the current setup, I have the state simply printing out to the screen.

                # os.system('clear')
                # print(self.button_data)
                # print(self.axis_data)
                # print(self.hat_data)

                # 0 = []
                # 1 = x
                # 2 = O
                # 3 = /\
                # 4 = L1
                # 5 = R1
                # 6 = L2
                # 7 = R2
                # 8 = share
                # 9 = options
                # 10= L3
                # 11= R3
                # 12 = PSbutton
                # 13 = touchpad
                
                if self.button_data[6] and self.button_data[7]:
                    print('Both R2 and L2 are pressed. Stopping the vehicle')
                    self.client.send_command(SOCKET_JOY_NEUTRAL)

                elif self.button_data[6]:
                    mapped_l2_value = np.interp(self.axis_data[4], (-1, 1), (0, 100))
                    print('Backwards', mapped_l2_value)
                    self.client.send_command(SOCKET_JOY_BACKWARD, mapped_l2_value)

                elif self.button_data[7]:
                    mapped_r2_value = np.interp(self.axis_data[5], (-1, 1), (0, 100))
                    print('Forward', mapped_r2_value)
                    self.client.send_command(SOCKET_JOY_FORWARD, mapped_r2_value)

                elif not self.button_data[6] and not self.button_data[7]:
                    print('Neutral')
                    self.client.send_command(SOCKET_JOY_NEUTRAL)


if __name__ == '__main__':
    joystick = Joystick()
    joystick.listen()