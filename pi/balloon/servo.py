"""Optional SG90 camera-pan servo on a Grove PWM port (default GPIO18 = port D18)."""
import logging

log = logging.getLogger("servo")


class Servo:
    def __init__(self, gpio=18):
        from gpiozero import AngularServo
        self.servo = AngularServo(gpio, min_angle=0, max_angle=180, min_pulse_width=0.0005, max_pulse_width=0.0025)
        self.angle = 90
        self.servo.angle = 90

    def set_angle(self, angle):
        angle = max(0.0, min(180.0, float(angle)))
        self.servo.angle = angle
        self.angle = angle
        log.info("servo -> %.0f", angle)
