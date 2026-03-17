import pika
import json
import datetime
import threading
from flask import Flask

app = Flask(__name__)

RABBIT_IP = '127.0.0.1'
QUEUE_NAME = 'management_queue'
SALES_FILE = 'sales_summary.txt'
PRODUCTION_FILE = 'production_summary.txt'


def save_sales_summary(total_sales, timestamp):
    # save the latest updates
    try:
        with open(SALES_FILE, 'w') as f:
            f.write(f"Last Update: {timestamp}\n")
            f.write(f"Total Sales: £{total_sales}\n")
    except IOError as e:
        print(f"Error saving sales summary: {e}")


def save_production_data(date, units_produced):
    # save production data
    try:
        # read existing data
        running_total = 0
        last_entry = None

        try:
            with open(PRODUCTION_FILE, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if line.startswith("Running Total:"):
                        running_total = int(line.split(':')[1].strip().replace(' units', ''))
                    elif line.startswith("Latest Entry:"):
                        last_entry = line
                        print(f"Last Entry: {last_entry}")
        except FileNotFoundError:
            pass

        # update running total
        running_total += units_produced

        # write updated data
        with open(PRODUCTION_FILE, 'w') as f:
            f.write(f"Latest Entry: {date} - {units_produced} units\n")
            f.write(f"Running Total: {running_total} units\n")

    except IOError as e:
        print(f"Error saving production data: {e}")


def callback(ch, method, properties, body):
    try:
        data = json.loads(body)
        origin = data.get('origin')

        if origin == 'accounts':
            # process accounts message
            total_sales = data.get('total_sales', 0)
            timestamp = data.get('timestamp', str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            save_sales_summary(total_sales, timestamp)
            print(f"[ACCOUNTS] Sales Update: £{total_sales} at {timestamp}")

        elif origin == 'engineering':
            # process engineering message
            date = data.get('date', 'Unknown')
            units_produced = data.get('units_produced', 0)
            save_production_data(date, units_produced)
            print(f"[ENGINEERING] Production Update: {units_produced} units on {date}")

        else:
            print(f"Unknown message origin: {origin}")

        ch.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError:
        print("Error: Received malformed message.")
        ch.basic_nack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"Error processing message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag)


@app.route('/report')
def generate_report():
    # generate a report with the latest sales data
    report = "<h2>Management Report</h2>"

    # read sales data
    try:
        with open(SALES_FILE, 'r') as f:
            sales_data = f.read()
            report += "<h3>Sales Summary</h3><pre>" + sales_data + "</pre>"
    except FileNotFoundError:
        report += "<h3>Sales Summary</h3><p>No sales data available yet.</p>"

    # read production data
    try:
        with open(PRODUCTION_FILE, 'r') as f:
            production_data = f.read()
            report += "<h3>Production Summary</h3><pre>" + production_data + "</pre>"
    except FileNotFoundError:
        report += "<h3>Production Summary</h3><p>No production data available yet.</p>"

    return report


def start_consumer():
    # start listening on management queue
    try:
        connection = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_IP))
        channel = connection.channel()
        channel.queue_declare(queue=QUEUE_NAME, durable=True)
        channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
        print("Management Office listening on management queue...")
        channel.start_consuming()
    except Exception as e:
        print(f"Fatal connection error in Management: {e}")


if __name__ == '__main__':
    # start the consumer thread
    consumer_thread = threading.Thread(target=start_consumer, daemon=True)
    consumer_thread.start()
    # start the Flask app
    print("Starting Flask app on port 5002 for reports...")
    app.run(host='0.0.0.0', port=5002)
