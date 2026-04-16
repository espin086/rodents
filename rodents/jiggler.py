import pyautogui
import numpy as np
import time
import keyboard
import logging
import random
import threading
import platform
import argparse
import atexit

# How long (seconds) the user must be idle before the jiggler resumes
IDLE_RESUME_SECONDS = 4 * 60  # 4 minutes

# Shared state protected by a lock
_activity_lock = threading.Lock()
_last_activity_time = None   # None means the jiggler has never been paused
_user_active = False         # True while the user is considered active (jiggler paused)


def _record_activity():
    """Record that the user just did something (key press or mouse move)."""
    global _last_activity_time, _user_active
    with _activity_lock:
        _last_activity_time = time.time()
        if not _user_active:
            logging.info("User activity detected – pausing jiggler.")
        _user_active = True


def _resume_jiggler():
    """Mark the jiggler as active again after the idle timeout has elapsed."""
    global _user_active
    with _activity_lock:
        _user_active = False


def _monitor_mouse(poll_interval=0.5):
    """
    Background thread: poll the mouse position every *poll_interval* seconds.
    If it has moved since the last poll, treat that as user activity.
    """
    prev_pos = pyautogui.position()
    while True:
        time.sleep(poll_interval)
        cur_pos = pyautogui.position()
        if cur_pos != prev_pos:
            _record_activity()
        prev_pos = cur_pos


def switch_to_next_tab():
    """
    Function to switch to the next tab.
    """
    if platform.system() == "Darwin":  # macOS
        pyautogui.hotkey("command", "shift", "[")
    elif platform.system() == "Windows":
        pyautogui.hotkey("ctrl", "tab")
    else:
        print("Unsupported operating system")


def move_mouse_to_position(x, y, duration):
    """
    Function to move the mouse to a specified position.
    """
    pyautogui.moveTo(x, y, duration=duration)


def switch_to_previous_tab():
    """
    Function to switch to the previous tab.
    """
    if platform.system() == "Darwin":  # macOS
        pyautogui.hotkey("command", "shift", "]")
    elif platform.system() == "Windows":
        pyautogui.hotkey("ctrl", "shift", "tab")
    else:
        print("Unsupported operating system")


def main(delay_mean, delay_std_dev, move_duration):
    """
    Main function to execute the program.

    The jiggler runs while the machine is idle.  As soon as the user moves the
    mouse or presses a key the jiggler pauses.  After the machine has been idle
    for IDLE_RESUME_SECONDS (4 minutes) the jiggler automatically resumes.
    """
    # Set up basic logging configuration
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Get screen size
    screen_width, screen_height = pyautogui.size()
    logging.info("Screen size: %d x %d", screen_width, screen_height)

    # Set the center of the screen as the center of the 2D normal distribution
    mean = (screen_width / 2, screen_height / 2)

    # Set the standard deviation for x and y coordinates
    std_dev_x = screen_width / 6
    std_dev_y = screen_height / 6

    # Define a list of commands using lambda expressions and their descriptions
    commands = [
        {
            "command": lambda: switch_to_next_tab(),
            "description": "Switched to the next tab",
        },
        {
            "command": lambda x, y, duration: move_mouse_to_position(x, y, duration),
            "description": "Moved mouse to position",
        },
        {
            "command": lambda: switch_to_previous_tab(),
            "description": "Switched to the previous tab",
        },
    ]

    # Register a keyboard hook so any key press is treated as user activity
    keyboard.on_press(lambda _: _record_activity())
    atexit.register(keyboard.unhook_all)

    # Start a background thread to detect mouse movement
    mouse_thread = threading.Thread(target=_monitor_mouse, daemon=True)
    mouse_thread.start()

    logging.info(
        "Jiggler started. It will pause on user activity and resume after %d minutes of idle.",
        IDLE_RESUME_SECONDS // 60,
    )

    while True:
        # Check whether the user is currently active
        with _activity_lock:
            active = _user_active
            idle_seconds = (
                time.time() - _last_activity_time if _last_activity_time is not None else None
            )

        if active:
            # Has the machine been idle long enough to resume?
            if idle_seconds is not None and idle_seconds >= IDLE_RESUME_SECONDS:
                _resume_jiggler()
                logging.info(
                    "Idle for %.0f seconds – resuming jiggler.", idle_seconds
                )
            else:
                remaining = (
                    IDLE_RESUME_SECONDS - idle_seconds
                    if idle_seconds is not None
                    else IDLE_RESUME_SECONDS
                )
                logging.debug("Jiggler paused. Resuming in %.0f seconds.", remaining)
                time.sleep(1)
                continue

        # --- Jiggler is active: perform a random action ---

        # Sample x and y coordinates from the 2D normal distribution
        x, y = np.random.multivariate_normal(
            mean, [[std_dev_x**2, 0], [0, std_dev_y**2]]
        )

        # Clamp the values to be within the screen boundaries
        x, y = max(0, min(x, screen_width - 1)), max(0, min(y, screen_height - 1))

        # Choose a random command from the commands list
        random_command = random.choice(commands)

        # Execute the random command
        if random_command["description"] == "Moved mouse to position":
            random_command["command"](x, y, move_duration)
        else:
            random_command["command"]()

        # Log the executed command
        logging.info("%s", random_command["description"])

        # Sample a delay from the normal distribution
        delay = max(0, np.random.normal(delay_mean, delay_std_dev))

        # Log the delay
        logging.info("Delaying next movement for %.2f seconds", delay)

        # Delay the next iteration (in small increments so activity is detected quickly)
        elapsed = 0.0
        while elapsed < delay:
            chunk = min(0.5, delay - elapsed)
            time.sleep(chunk)
            elapsed += chunk
            with _activity_lock:
                if _user_active:
                    break


def run_jiggler():
    parser = argparse.ArgumentParser(
        description="This program moves the mouse cursor randomly on the screen and performs random actions such as switching tabs or clicking on buttons."
    )
    parser.add_argument(
        "--delay_mean",
        type=float,
        default=12,
        help="Mean value for delay distribution",
    )
    parser.add_argument(
        "--delay_std_dev",
        type=float,
        default=6,
        help="Standard deviation for delay distribution",
    )
    parser.add_argument(
        "--move_duration",
        type=float,
        default=0.5,
        help="Duration of the mouse movement in seconds",
    )
    args = parser.parse_args()

    main(args.delay_mean, args.delay_std_dev, args.move_duration)


run_jiggler()
