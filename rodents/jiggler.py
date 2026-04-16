import pyautogui
import numpy as np
import time
import keyboard
import logging
import random
import threading
import platform
import argparse
import datetime


# --- Global state for hotkey toggle and working-hours scheduler ---
running = False
manually_stopped = False
_state_lock = threading.Lock()


def _set_running(value, reason):
    """Thread-safe helper to set the running flag and log a status message."""
    global running
    with _state_lock:
        running = value
    if value:
        logging.info("Mouse movement STARTED – %s", reason)
    else:
        logging.info("Mouse movement STOPPED – %s", reason)


def toggle_movement():
    """Toggle mouse movement on/off in response to a hotkey press."""
    global manually_stopped, running
    with _state_lock:
        new_state = not running  # read and compute while holding the lock
        running = new_state
        manually_stopped = not new_state  # True when user just stopped it
    if new_state:
        logging.info("Mouse movement STARTED – hotkey toggle")
    else:
        logging.info("Mouse movement STOPPED – hotkey toggle")


def is_working_hours(start_time, end_time):
    """Return True if the current local time is within the working-hours window.

    Supports both same-day ranges (e.g. 09:00–18:00) and overnight ranges
    that span midnight (e.g. 22:00–06:00).
    """
    now = datetime.datetime.now().time()
    if start_time <= end_time:
        # Normal same-day range
        return start_time <= now <= end_time
    # Overnight range: active from start_time until midnight AND from midnight until end_time
    return now >= start_time or now <= end_time


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


def _movement_loop(mean, std_dev_x, std_dev_y, delay_mean, delay_std_dev, move_duration, commands, screen_width, screen_height):
    """Background thread: performs mouse actions whenever *running* is True."""
    while True:
        with _state_lock:
            should_run = running

        if not should_run:
            time.sleep(1)
            continue

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
        delay = np.random.normal(delay_mean, delay_std_dev)

        # Clamp the delay to be non-negative
        delay = max(0, delay)

        # Log the delay
        logging.info("Delaying next movement for %.2f seconds", delay)

        # Delay the next iteration
        time.sleep(delay)


def main(delay_mean, delay_std_dev, move_duration, start_time, end_time):
    """
    Main function to execute the program.
    """
    global manually_stopped

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

    # Register hotkey: Cmd+M on macOS, Ctrl+M elsewhere
    hotkey = "command+m" if platform.system() == "Darwin" else "ctrl+m"
    keyboard.add_hotkey(hotkey, toggle_movement)
    logging.info("Hotkey registered: %s  (toggle mouse movement)", hotkey)
    logging.info(
        "Working hours: %s – %s",
        start_time.strftime("%H:%M"),
        end_time.strftime("%H:%M"),
    )

    # Start the movement loop in a background daemon thread
    move_thread = threading.Thread(
        target=_movement_loop,
        args=(mean, std_dev_x, std_dev_y, delay_mean, delay_std_dev, move_duration, commands, screen_width, screen_height),
        daemon=True,
    )
    move_thread.start()

    # Main scheduling loop: check working hours every 30 seconds
    last_in_work_hours = None
    while True:
        in_hours = is_working_hours(start_time, end_time)

        if in_hours:
            # Start automatically if we just entered working hours and user
            # hasn't manually stopped it
            if last_in_work_hours is False:
                # New working-hours period began – clear any prior manual stop
                with _state_lock:
                    manually_stopped = False
            if not manually_stopped:
                with _state_lock:
                    already_running = running
                if not already_running:
                    _set_running(True, "working hours started")
        else:
            # Outside working hours – always stop movement
            with _state_lock:
                already_running = running
            if already_running:
                _set_running(False, "working hours ended")
            # Reset manual-stop flag so the next working-hours window auto-starts
            with _state_lock:
                manually_stopped = False

        last_in_work_hours = in_hours
        time.sleep(30)


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
    parser.add_argument(
        "--start-time",
        type=str,
        default="09:00",
        help="Working hours start time in HH:MM format (default: 09:00)",
    )
    parser.add_argument(
        "--end-time",
        type=str,
        default="18:00",
        help="Working hours end time in HH:MM format (default: 18:00)",
    )
    args = parser.parse_args()

    try:
        start_time = datetime.datetime.strptime(args.start_time, "%H:%M").time()
        end_time = datetime.datetime.strptime(args.end_time, "%H:%M").time()
    except ValueError:
        parser.error(
            "Invalid time format. Please use HH:MM (e.g. --start-time 09:00 --end-time 18:00)."
        )

    main(args.delay_mean, args.delay_std_dev, args.move_duration, start_time, end_time)


run_jiggler()
