import pika
import json
from flask import Flask, request
import datetime

app = Flask(__name__)

RABBIT_IP = '127.0.0.1'
QUEUE_NAME = 'management_queue'
PERSISTENCE_FILE = 'production_data.txt'


def get_last_production_entry():
    # read last production entry from file
    try:
        with open(PERSISTENCE_FILE, 'r') as f:
            lines = f.readlines()
            if lines:
                return lines[-1].strip()
    except FileNotFoundError:
        pass
    return None


def save_production_entry(date, units):
    # save production entry to the file
    try:
        with open(PERSISTENCE_FILE, 'a') as f:
            f.write(f"{date} : {units} units\n")
    except IOError as e:
        print(f"Error saving production data: {e}")


def send_to_queue(payload):
    connection = None
    try:
        parameters = pika.ConnectionParameters(
            host=RABBIT_IP,
            port=5672,
            virtual_host='/',
            credentials=pika.PlainCredentials('guest', 'guest')
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        channel.queue_declare(queue=QUEUE_NAME, durable=True)

        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        return True

    except pika.exceptions.AMQPConnectionError:
        print(f"CRITICAL: Could not connect to RabbitMQ at {RABBIT_IP}.")
        return False
    except pika.exceptions.AuthenticationError:
        print("CRITICAL: Invalid credentials for RabbitMQ.")
        return False
    except Exception as e:
        print(f"CRITICAL: Unexpected error: {type(e).__name__}: {e}")
        return False
    finally:
        if connection and connection.is_open:
            connection.close()


@app.route('/', methods=['GET', 'POST'])
def engineering_portal():
    if request.method == 'POST':
        try:
            date_str = request.form.get('date', '').strip()
            units_raw = request.form.get('units', '').strip()

            if not date_str or not units_raw:
                return "Invalid input: all fields are required.", 400

            units = int(units_raw)
            if units < 0:
                return "Invalid input: units must be positive.", 400

            # save to file
            save_production_entry(date_str, units)

            # send to management queue
            data = {
                "origin": "engineering",
                "date": date_str,
                "units_produced": units,
                "timestamp": str(datetime.datetime.now())
            }

            if not send_to_queue(data):
                return "Could not connect to RabbitMQ.", 503

            return "Production Data Sent to Management!"

        except ValueError:
            return "Error: Units must be a number.", 400
        except Exception as e:
            print(f"Unhandled POST error: {type(e).__name__}: {e}")
            return "Internal application error.", 500
# web form
    return '''
        <h2>Engineering Office - Daily Production Data</h2>
        <form method="POST">
            Date: <input type="date" name="date" required><br>
            Units Produced: <input type="number" name="units" required><br>
            <input type="submit" value="Submit Production Data">
        </form>
    '''


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
