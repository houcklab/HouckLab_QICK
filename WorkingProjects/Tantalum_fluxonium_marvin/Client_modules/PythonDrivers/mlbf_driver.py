import socket
import logging
import re
import time

class MLBFDriver:
    def __init__(self, ip_address, udp_port=30303, timeout=5):
        """Initialize the connection to the MLBF filter over UDP."""
        self.ip_address = ip_address
        self.udp_port = udp_port
        self.buffer_size = 1024
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(timeout)  # Set a timeout to avoid indefinite blocking

    def send_command(self, command, expect_response=True):
        """Send a command to the MLBF filter, optionally waiting for a response."""
        message = command.encode('ascii')
        # logging.info(f"Sending command: {command}")  # Log the sent command
        self.sock.sendto(message, (self.ip_address, self.udp_port))

        if expect_response:
            try:
                data, _ = self.sock.recvfrom(self.buffer_size)
                # logging.info(f"Received response: {data.decode('ascii')}")  # Log the received response
                return data.decode('ascii')
            except socket.timeout:
                logging.error(f"Timeout: No response from the filter for command '{command}'")
                return None  # Return None or raise an exception, depending on your needs

    def set_frequency(self, frequency):
        """Set the filter's frequency in MHz. No response is expected."""
        # THIS DOES NOT ALWAYS WORK. Make sure to check the frequency has actually been changed!
        # This is really a crutch, but I am too lazy to figure out what the actual problem is.
        command = f"F{frequency:.3f}"  # Ensure format is 'Fxxxxxx.xxx'
        for i in range(5):
            self.send_command(command, expect_response=False)
            time.sleep(0.1)
            cur_freq = self.get_frequency()
            if cur_freq == frequency:
                print("Frequency set to %.3f" % cur_freq)
                return
            print("Frequency not set successfully! Trying again...")
        raise Exception("Can't get the frequency to set correctly in 5 tries!")

    def get_status(self):
        """Retrieve the current status of the filter."""
        return self.send_command("?")

    def get_temperature(self):
        """Retrieve the current internal temperature of the MLBF filter."""
        return self.send_command("T")

    def get_frequency(self):
        """Get the current frequency setting and return it as a float."""
        response = self.send_command("R0016")  # Send command to get frequency

        if response:
            # Clean the response by stripping unwanted characters
            match = re.search(r"(\d+\.\d+)", response)

            try:
                # Convert the cleaned response to a float
                frequency_value = float(match.group(1))
                print(f"Current frequency: {frequency_value} MHz")
                return frequency_value
            except ValueError:
                logging.error(f"Failed to convert frequency response to float: {match.group(1)}")
                return None
        else:
            logging.error("No response received for frequency query.")
            return None

    def close(self):
        """Close the UDP socket."""
        self.sock.close()


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)  # Enable logging
    driver = MLBFDriver("192.168.1.11")  # Use the correct IP for the filter
    driver.set_frequency(6000.0)  # Set frequency to 6000 MHz
    # print(driver.get_status())  # Retrieve status
    # print(driver.get_temperature())  # Retrieve temperature
    # frequency = driver.get_frequency()  # Get the current frequency as a float

    driver.close()