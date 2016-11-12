#!/usr/bin/env python2.7

"""
Columbia W4111 Intro to databases
Example webserver
To run locally
    python server.py
Go to http://localhost:8111 in your browser
A debugger such as "pdb" may be helpful for debugging.
Read about it online.
"""

import os
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response

from collections import OrderedDict

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)


DATABASEURI = "postgresql://ar3567:39xbn@104.196.175.120/postgres"


#
# This line creates a database engine that knows how to connect to the URI above
#
engine = create_engine(DATABASEURI)


@app.before_request
def before_request():
    """
    This function is run at the beginning of every web request
    (every time you enter an address in the web browser).
    We use it to setup a database connection that can be used throughout the request
    The variable g is globally accessible
    """
    try:
        g.conn = engine.connect()

    except:
        print "uh oh, problem connecting to database"
        import traceback; traceback.print_exc()
        g.conn = None

@app.teardown_request
def teardown_request(exception):
    """
    At the end of the web request, this makes sure to close the database connection.
    If you don't the database could run out of memory!
    """
    try:
        g.conn.close()
    except Exception as e:
        pass


@app.route('/')
def index():
    """
    request is a special object that Flask provides to access web request information:
    request.method:   "GET" or "POST"
    request.form:     if the browser submitted a form, this contains the data in the form
    request.args:     dictionary of URL arguments e.g., {a:1, b:2} for http://localhost?a=1&b=2
    See its API: http://flask.pocoo.org/docs/0.10/api/#incoming-request-data
    """

    return render_template("index.html")


@app.route('/login', methods=['POST'])
def login():
    email = '' if request.form['email'] is None else request.form['email']
    password = '' if request.form['password'] is None else request.form['password']
    cmd = """SELECT p.name, c.password, c.pid FROM "Person" p NATURAL JOIN "Customer" c WHERE c.email=%s;"""
    cursor = g.conn.execute(cmd, (email,))
    record = cursor.first()
    if not record:
        context = dict(error_email='Invalid user email. Please sign up.')
    else:
        if not record[1] == password:
            context = dict(error_password='Incorrect password, try again.')
        else:
            context = dict(user=record[0], uid=record[2])

    return render_template('index.html', **context)


@app.route('/register', methods=['POST'])
def register():
    name = request.form['name']
    phone = long(request.form['phone'])
    email = request.form['email']
    password = request.form['password']

    check_cmd = """SELECT email FROM "Customer" WHERE email=%s"""
    cursor = g.conn.execute(check_cmd, (email,))

    # User email already exists
    if cursor.first():
        return redirect('/')

    cmd = """
        WITH new_person AS (
            INSERT INTO "Person" (name) VALUES (%s)
            RETURNING pid
        )
        INSERT INTO "Customer" (
            pid, phone, email, password
        ) VALUES ((SELECT pid from new_person), %s, %s, %s);
    """

    g.conn.execute(cmd, (name, phone, email, password))

    return redirect('/')


@app.route('/menu')
def display_menu():

    cursor = g.conn.execute('SELECT * FROM "Item";')
    menu_items = OrderedDict([
        ('Starters', []),
        ('Soups and Salads', []),
        ('Rice', []),
        ('Breads', []),
        ('Vegetables', []),
        ('Chicken', []),
        ('Lamb', []),
        ('Seafood', []),
        ('Tandoori Specialties', []),
        ('Sides', []),
        ('Desserts', [])
    ])
    for result in cursor:
        item = {}
        item['name'] = result['name']
        item['desc'] = result['description']
        item['price'] = result['price']
        menu_items[result['category']].append(item)
    cursor.close()

    context = dict(menu=menu_items)

    return render_template("menu.html", **context)


@app.route('/reviews')
def display_feedback():

    cursor = g.conn.execute("""SELECT * FROM "Feedback" NATURAL JOIN "Person" WHERE NOT review='';""")
    feedback = []
    for result in cursor:
        review = {}
        review['review'] = result['review']
        review['rating'] = result['rating']
        review['reviewer'] = result['name']
        review['date'] = result['date']
        feedback.append(review)

    cursor = g.conn.execute('SELECT AVG(rating) FROM "Feedback"')
    context = dict(feedback=feedback, avgRating='%.2f' % cursor.first()[0])
    cursor.close()

    return render_template("feedback.html", **context)


@app.route('/orders/<uid>')
def view_orders(uid):

    cursor = g.conn.execute("""SELECT * FROM "Order_Delivery_Person" NATURAL JOIN
                                (SELECT oid, date, delivery_address, status, type, number
                                FROM "Order" NATURAL JOIN "Card" c
                                WHERE cust_id=%s ORDER BY date DESC) AS "Order" """, (uid,))
    orders = []
    for result in cursor:
        order = {}
        order['oid'] = result['oid']
        order['date'] = result['date']
        order['address'] = result['delivery_address']
        order['status'] = result['status']
        order['card_details'] = {
            'type': result['type'],
            'number': 'XXXX-XXXX-XXXX-'+str(result['number'])[12:]
        }
        order_cursor = g.conn.execute("""SELECT name, price, quantity, price*quantity AS item_total
                                            FROM "Order_Item" NATURAL JOIN "Item" WHERE oid=%s;""", (result['oid'], ))
        order_subtotal = 0.0
        order['item_details'] = []

        for item in order_cursor:
            item_details = {}
            item_details['name'] = item['name']
            item_details['price'] = item['price']
            item_details['quantity'] = item['quantity']
            item_details['item_total'] = item['item_total']
            order['item_details'].append(item_details)
            order_subtotal += float(item['item_total'])

        order['subtotal'] = order_subtotal
        order['tip'] = result['tip']
        order['tax'] = float('%.2f' % (0.1*order_subtotal))
        order['delivery_fee'] = 5.0
        order['total'] = order_subtotal + float(order['tip']) + order['tax'] + order['delivery_fee']

        order_cursor = g.conn.execute("""SELECT name FROM "Person" WHERE pid=%s;""", (result['did'],))
        order['delivery_person'] = order_cursor.first()['name']

        orders.append(order)
        order_cursor.close()

    context = dict(orders=orders)
    cursor.close()

    return render_template("orders.html", **context)


if __name__ == "__main__":
    import click

    @click.command()
    @click.option('--debug', is_flag=True)
    @click.option('--threaded', is_flag=True)
    @click.argument('HOST', default='0.0.0.0')
    @click.argument('PORT', default=8111, type=int)
    def run(debug, threaded, host, port):
        """
        This function handles command line parameters.
        Run the server using
            python server.py
        Show the help text using
            python server.py --help
        """

        HOST, PORT = host, port
        print "running on %s:%d" % (HOST, PORT)
        app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)


    run()