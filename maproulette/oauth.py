#!/usr/bin/python
import json
from maproulette import app, models
from flask_oauth import OAuth
from flask import request, url_for, redirect, session
from flask.ext.sqlalchemy import SQLAlchemy
from maproulette.database import db
from geoalchemy2.elements import WKTElement

# instantite OAuth object
oauth = OAuth()
osm = oauth.remote_app(
    'osm',
    base_url = app.config['OSM_URL'] + 'api/0.6/',
    request_token_url = app.config['OSM_URL'] + 'oauth/request_token',
    access_token_url = app.config['OSM_URL'] + 'oauth/access_token',
    authorize_url = app.config['OSM_URL'] + 'oauth/authorize',
    consumer_key = app.config['OAUTH_KEY'],
    consumer_secret = app.config['OAUTH_SECRET']
)

@osm.tokengetter
def get_osm_token(token=None):
    session.regenerate()
    return session.get('osm_token')

@app.route('/oauth/authorize')
def oauth_authorize():
    """Initiates OAuth authorization agains the OSM server"""
    return osm.authorize(callback=url_for('oauth_authorized',
      next=request.args.get('next') or request.referrer or None))

@app.route('/oauth/callback')
@osm.authorized_handler
def oauth_authorized(resp):
    """Receives the OAuth callback from OSM"""
    next_url = request.args.get('next') or url_for('index')
    if resp is None:
        return redirect(next_url)
    session['osm_token'] = (
      resp['oauth_token'],
      resp['oauth_token_secret']
    )
    data = osm.get('user/details').data
    app.logger.debug("Getting user data from osm")
    if not data:
        # FIXME this requires handling
        return False
    userxml = data.find('user')
    osmid = userxml.attrib['id']
    # query for existing user
    if bool(models.User.query.filter(models.User.id==osmid).count()):
        #user exists
        user = models.User.query.filter(models.User.id==osmid).first()
    else:
        # create new user
        user = models.User()
        user.id = osmid
        user.display_name = userxml.attrib['display_name']
        user.osm_account_created = userxml.attrib['account_created']
        homexml = userxml.find('home')
        if homexml is not None:
            user.home_location = WKTElement('POINT(%s %s)' % (homexml.attrib['lon'], homexml.attrib['lat']))
        else:
            app.logger.debug('no home for this user')
        languages = userxml.find('languages')
        #FIXME parse languages and add to user.languages string field
        user.changeset_count = userxml.find('changesets').attrib['count']
        # get last changeset info
        try:
            changesetdata = osm.get('changesets?user=%i' % (user.id)).data
            lastchangeset = changesetdata.find('changeset')
            if 'min_lon' in lastchangeset:
                user.last_changeset_bbox = 'POLYGON((%s %s, %s %s, %s %s, %s %s, %s %s))' % (
                        lastchangeset.attrib['min_lon'],
                        lastchangeset.attrib['min_lat'],
                        lastchangeset.attrib['min_lon'],
                        lastchangeset.attrib['max_lat'],
                        lastchangeset.attrib['max_lon'],
                        lastchangeset.attrib['max_lat'],
                        lastchangeset.attrib['max_lon'],
                        lastchangeset.attrib['min_lat'],
                        lastchangeset.attrib['min_lon'],
                        lastchangeset.attrib['min_lat'])
                user.last_changeset_date = lastchangeset.attrib['created_at']
        except:
            app.logger.debug('could not get changeset data from osm.')
        db.session.add(user)
        db.session.commit()
        app.logger.debug('user created')
    session['display_name'] = user.display_name
    session['osm_id'] = user.id
    session['home_location'] = user.home_location
    session['difficulty'] = user.difficulty
    return redirect(next_url)
