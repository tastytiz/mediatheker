# 🍿 Mediatheker

This app serves as a newsletter application which matches the latest recommended movies of the three different German public broadcasters ARD, ZDF, and ARTE with iMDb. It thereafter sends out the latest movies based on the individual rating settings of the subscribers.

The development of this application had three main motivations:

1. Proof of concept for an e-mail only application
2. Making the movies available for download (.mp4/.webm) using the broadcasters' APIs
2. Raising awareness that the rather dusty German public broadcasters do actually serve decent movies for free


## What does Mediatheker actually do?

The application is split up into two separate programs:

1. The *mediatheker.py* does the actual brain work by retrieving the movies of the broadcasters' websites, matchmaking with iMDb and sending out the newsletters to subscribers
2. The *mail_service.py* handles all user interaction. So whenever a user sends a mail to the application this script knows the answer (see commands in the next section).

The *mediatheker.py* scrapes the websites of the broadasters' movie libraries and searches for the latest recommended movies on each site. It saves each movie into a dict with all relevant information it finds on the website. This info is then enriched by making different API calls to ultimately the best download link for a given movie. Finally, it tries to match each movie with the iMDb database to get a rating, iMDb-id, country and year information, and a cover image.

Once all movies are retrieved and enriched, they are stored in a TinyDB database and compared to the previous day's movies. Only the new movies are then sent out to the subscribers depending on their individual rating threshold. E.g. a user with a 6.0 threshold will receive more movies each day than a user with a 7.0 iMDb-rating threshold.

The *mail_service.py* retrieves the mails sent to the service's mail address and tries to handle the requests of the users. See the next chapter for a more detailed overview.

## How can a user interact?

By making it an e-mail only application a user can interact with the newsletter by replying/sending mails to the application's e-mail address. There are 5 different commands available for a regular user:

| Command | Description |
| ----------- | ----------- |
| *Subscribe* | Registers a new user |
| e.g. *7.6* | Sets a subscriber's iMDb-rating to the given number |
| *Summary* | Sends out a summary of all movies available matching the subscriber's iMDb-rating |
| *All* | Sends out a summary of all movies available |
| *Stop* | Unsubscribes a user |

## How can the admin interact?

There are two mail commands only the admin of the service can use:

| Command | Description |
| ----------- | ----------- |
| *Rerun* | Rerun the script in case the retrieval of new movies failed |
| *Download + ID* | Download a specific movie onto the application's server |


Besides the *mediatheker.py* app can be run with different arguments:

````
-l, --load          Used to retrieve new movies + send them out to the subscribers
-sub, --subscribers List all subscribers
-s, --score         Returns list of available movies and their iMDb matchmaking scores
-g, --get_movies    Search & return for specific movie in database using its title
-a, --admin         Sets the admin of the service
````

E.g. 
```console
foo@bar:~/mediatheker $ python3 mediatheker.py -g "Der Hauptmann"
{
  "title": "Der Hauptmann",
  "url": "https://www.zdf.de/filme/der-hauptmann-112.html",
  "download_url": "https://nrodlzdf-a.akamaihd.net/dach/3sat/20/05/200508_der_hauptmann_spielfilm/2/200508_der_hauptmann_spielfilm_1496k_p13v13.mp4",
  "plot": "Ende des Zweiten Weltkriegs findet der junge Gefreite Willi Herold auf der Flucht eine Hauptmannsuniform. Kurzerhand \u00fcbernimmt er die ranghohe Bekleidung und die damit verbundene Rolle. (FSK 16)",
  "runtime": 114,
  "channel": "zdf",
  "unique": "derhauptmannzdf114",
  "language": "",
  "cover_url": "https://m.media-amazon.com/images/M/MV5BY2NiOGRlZDEtNDM5NS00OWQ0LTlkNzctMWZlMTkzNWJhZTNhXkEyXkFqcGdeQXVyODg5NTg2NDU@._V1_SY150_CR0,0,101,150_.jpg",
  "year": 2017,
  "countries": "Germany, France, Poland, China, Portugal",
  "genres": "Drama, History, Thriller, War",
  "rating": 7.4,
  "imdbID": "6763252",
  "score": 9.0,
  "type": "old",
  "movie_id": 31
}
```

## How to install it?

Requirements:
- python 3.6 or above 
- a mail address with IMAP + SMTP access

Recommendation:
- A Linux server which support cronjobs or similar in order to let the service run on a regular basis

Installing the app is rather simple:
1. Clone this repository
2. Depending on your system run `python3 mediatheker.py` or `python mediatheker.py`
3. Follow the initial setup (Linux is beneficial here as the setup will allow you to install a cronjob right away)
4. Success
