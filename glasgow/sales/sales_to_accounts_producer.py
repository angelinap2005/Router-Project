import pika
import json
from flask import Flask, request

app = Flask(__name__)

RABBIT_IP = '127.0.0.1'
QUEUE_NAME = 'sales_to_accounts'

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
def sales_portal():
    if request.method == 'POST':
        try:
            # get the customer name, invoice number, and value
            customer = request.form.get('customer', '').strip()
            inv_no = request.form.get('inv_no', '').strip()
            value_raw = request.form.get('value', '').strip()

            # validate input
            if not customer or not inv_no or not value_raw:
                return "Invalid input: all fields are required.", 400

            value = float(value_raw)
            if value < 0:
                return "Invalid input: value must be positive.", 400

            data = {
                "customer": customer,
                "invoice_no": inv_no,
                "amount": value
            }

            if not send_to_queue(data):
                return "Could not connect to RabbitMQ.", 503

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
            Invoice #: <input type="text" name="inv_no"><br>
            Value (Excl VAT): <input type="text" name="value"><br>
            <input type="submit" value="Submit Invoice">
        </form>
    '''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)