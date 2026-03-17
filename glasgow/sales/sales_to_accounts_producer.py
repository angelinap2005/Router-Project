import pika
import json
from flask import Flask, request

app = Flask(__name__)

RABBIT_IP = '127.0.0.1'
QUEUE_NAME = 'sales_to_accounts'
INVOICE_FILE = 'last_invoice.txt'


def get_next_invoice_number():
    try:
        with open(INVOICE_FILE, 'r') as f:
            content = f.read().strip()
            # remove any leading zeros or padding
            last_invoice = int(content)
    except (FileNotFoundError, ValueError):
        last_invoice = 0

    next_invoice = last_invoice + 1
    # pad the invoice number with leading zeros for consistency
    padded_invoice = str(next_invoice).zfill(4)

    with open(INVOICE_FILE, 'w') as f:
        f.write(padded_invoice)

    return padded_invoice


def send_to_queue(payload):
    connection = None
    try:
        # connect to rabbitmq using a default guest account
        parameters = pika.ConnectionParameters(
            host=RABBIT_IP,
            port=5672,
            virtual_host='/',
            credentials=pika.PlainCredentials('guest', 'guest')
        )
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        # durable=True ensures the queue survives a RabbitMQ restart
        channel.queue_declare(queue=QUEUE_NAME, durable=True)

        channel.basic_publish(
            exchange='',
            routing_key=QUEUE_NAME,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        return True
    # exception handling for common RabbitMQ connection issues
    except pika.exceptions.AMQPConnectionError:
        print(f"CRITICAL: Could not connect to RabbitMQ at {RABBIT_IP}. Check Router/Firewall.")
        return False
    except pika.exceptions.AuthenticationError:
        print("CRITICAL: Invalid credentials for RabbitMQ.")
        return False
    except pika.exceptions.ChannelClosedByBroker:
        print("CRITICAL: The broker closed the channel. Check if the queue name is valid.")
        return False
    except Exception as e:
        print(f"CRITICAL: Unexpected error: {type(e).__name__}: {e}")
        return False
    finally:
        # close the connection
        if connection and connection.is_open:
            connection.close()


@app.route('/', methods=['GET', 'POST'])
def sales_portal():
    # request object is submitted
    if request.method == 'POST':
        try:
            # extract inputted values and validate
            customer = request.form.get('customer', '').strip()
            value_raw = request.form.get('value', '').strip()

            if not customer or not value_raw:
                return "Invalid input: all fields are required.", 400

            value = float(value_raw)
            # assumption: sales are always positive
            if value < 0:
                return "Invalid input: value must be positive.", 400
            # dynamically generate invoice number
            inv_no = get_next_invoice_number()
            # data to be sent to accounts
            data = {
                "customer": customer,
                "invoice_no": inv_no,
                "amount": value
            }
            # send it to accounts
            if not send_to_queue(data):
                return "Could not connect to RabbitMQ.", 503
            # confirmation
            return "Invoice Sent to Accounts!"

        except (ValueError, TypeError):
            return "Error: Sales value must be a number.", 400
        except Exception as e:
            print(f"Unhandled POST error: {type(e).__name__}: {e}")
            return "Internal application error.", 500

    return '''
        <h2>Sales Office - New Invoice</h2>
        <form method="POST">
            Customer: <input type="text" name="customer"><br>
            Value (Excl VAT): <input type="text" name="value"><br>
            <input type="submit" value="Submit Invoice">
        </form>
    '''


if __name__ == '__main__':
    # run the Flask app on all interfaces
    app.run(host='0.0.0.0', port=5000)