import pika
import json
import datetime

RABBIT_IP = '127.0.0.1'
IN_QUEUE = 'sales_to_accounts'
OUT_QUEUE = 'management_queue'
PERSISTENCE_FILE = 'running_invoice_total.txt'

def get_global_corporate_total():
    # calculate the total number of all invoices from the persistence file
    global_total = 0.0
    try:
        with open(PERSISTENCE_FILE, 'r') as f:
            for line in f:
                if ':' in line:
                    parts = line.split(':')
                    # format: "CustomerName : £Total Last Invoice No.: InvoiceNo"
                    amount_part = parts[1].strip().replace('£', '').split()[0]
                    global_total += float(amount_part)
    except FileNotFoundError:
        pass
    return global_total

def get_running_total_for_customer(customer):
    try:
        with open(PERSISTENCE_FILE, 'r') as f:
            for line in f:
                if customer in line and ':' in line:
                    # format: "CustomerName : £Total Last Invoice No.: InvoiceNo"
                    parts = line.split(':')
                    amount_part = parts[1].strip().replace('£', '').split()[0]
                    return float(amount_part)
            return None  # Customer not found
    except (FileNotFoundError, ValueError, IOError):
        return 0.0  # File doesn't exist, first invoice


def save_total(new_total, customer, invoice_no):
    try:
        # read existing customers
        customers = {}
        try:
            with open(PERSISTENCE_FILE, 'r') as f:
                for line in f:
                    if ':' in line:
                        parts = line.split(':')
                        cust_name = parts[0].strip()
                        customers[cust_name] = line.strip()
        except FileNotFoundError:
            pass

        # update the customer's total or add a new entry
        customers[customer] = f"{customer} : £{new_total} Last Invoice No.: {invoice_no}"

        # write all the customers back to the file
        with open(PERSISTENCE_FILE, 'w') as f:
            for cust_line in customers.values():
                f.write(cust_line + '\n')
    except IOError as e:
        # exception handling for file I/O errors
        print(f"Critical Error: Failed to write to persistence file: {e}")


def notify_management(total):
    try:
        # notify management of the new total
        connection = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_IP))
        channel = connection.channel()
        channel.queue_declare(queue=OUT_QUEUE, durable=True)

        # message structure is {"origin": "accounts", "total_sales": total, "timestamp": timestamp}
        update = {
            "origin": "accounts",
            "total_sales": total,
            "timestamp": str(datetime.datetime.now())
        }
        # send the message to the management queue
        channel.basic_publish(exchange='', routing_key=OUT_QUEUE, body=json.dumps(update))
        connection.close()
    except pika.exceptions.AMQPError as e:
        print(f"Network error while notifying management: {e}")


def callback(ch, method, properties, body):
    try:
        data = json.loads(body)
        if not isinstance(data, dict) or data is None:
            print("Error: Message is not a valid JSON object.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        amount = data.get('amount')
        customer = data.get('customer')
        invoice_no = data.get('invoice_no')

        if amount is None or customer is None or invoice_no is None:
            print("ERROR: Missing required fields in message.")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        else:
            amount = float(amount)
            invoice_no = str(invoice_no).strip()
            customer = customer.strip()

            # save the running total for the customer
            customer_total = get_running_total_for_customer(customer)
            if customer_total is None:
                save_total(amount, customer, invoice_no)
            else:
                new_total = customer_total + amount
                save_total(new_total, customer, invoice_no)

            # calculate the global corporate total
            global_total = get_global_corporate_total()

            # send the updated global total to management
            notify_management(global_total)

            print(f"Processed Invoice {invoice_no} for {customer}.")
            print(f"Global Corporate Total Updated to: £{global_total}")

            ch.basic_ack(delivery_tag=method.delivery_tag)

    except json.JSONDecodeError:
        print("Error: Invalid JSON message.")
        ch.basic_nack(delivery_tag=method.delivery_tag)

try:
    # connect to rabbitmq
    conn = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_IP))
    chan = conn.channel()
    chan.queue_declare(queue=IN_QUEUE, durable=True)
    chan.basic_consume(queue=IN_QUEUE, on_message_callback=callback)
    # confirm the queue has started
    print("Accounts Office is listening on the Sales Queue...")
    chan.start_consuming()
except Exception as e:
    print(f"Fatal connection error in Accounts: {e}")