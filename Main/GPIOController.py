import settings
import os
from Controller import Controller
from Actuator import Actuator

# noinspection PyUnresolvedReferences
import RPi.GPIO as GPIO


class GPIOController(Controller):
    def __init__(self):
        GPIO.setmode(GPIO.BOARD)
        self.left = Actuator(
            pin_forward=int(os.getenv('PIN_LEFT_FORWARD')),
            pin_backward=int(os.getenv('PIN_LEFT_BACKWARD')),
            pin_pwm=int(os.getenv('PIN_LEFT_PWM'))
        )

        self.right = Actuator(
            pin_forward=int(os.getenv('PIN_RIGHT_FORWARD')),
            pin_backward=int(os.getenv('PIN_RIGHT_BACKWARD')),
            pin_pwm=int(os.getenv('PIN_RIGHT_PWM'))
        )

    def forward(self, power=100):
        self.left.forward(power)
        self.right.forward(power)

    def reverse(self, power=100):
        self.left.reverse(power)
        self.right.reverse(power)

    def neutral(self):
        self.left.neutral()
        self.right.neutral()

    def exit(self):
        self.left.exit()
        self.right.exit()
        GPIO.cleanup()