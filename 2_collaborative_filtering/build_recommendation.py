import pyspark as ps
from pyspark.mllib.recommendation import ALS, MatrixFactorizationModel, Rating
from get_data import get_data_from_mongodb
import numpy as np
import pandas as pd
from scipy import sparse
import cPickle as pickle
from collections import defaultdict
import fuzzywuzzy


def get_ratings_contents(save_pickle=False):
    games_df = get_data_from_mongodb()
    game_names = pd.factorize(games_df.game_name)
    critics = pd.factorize(games_df.critic)

    if save_pickle:
    #     with open('data/critics.pkl', 'wb') as f_critic:
    #         pickle.dump(critics, f_critic)

        with open('data/game_names.pkl', 'wb') as f_games:
            pickle.dump(game_names[1], f_games)

    ratings_contents = games_df[ ['score'] ].astype(float)
    ratings_contents.loc[:, 'game'] = pd.Series(game_names[0])
    ratings_contents.loc[:, 'user'] = pd.Series(critics[0])

    return ratings_contents[ ['user', 'game', 'score'] ]


def ratings_to_file():
    ratings = get_ratings_contents()
    ratings_text = ratings.to_csv(header=False, index=False)
    with open('data/ratings.txt', 'wb') as f:
        f.write(ratings_text)


def get_ratings_data(ratings_contents):
    total_users = len(ratings_contents.user.unique())
    total_games = len(ratings_contents.game.unique())
    ratings_mat = sparse.lil_matrix((total_users, total_games))

    for _, row in ratings_contents.iterrows():
        ratings_mat[row.user, row.game] = row.score

    return ratings_mat


def create_spark_ratings():
    sc = ps.SparkContext('local[4]')

    # Load and parse the data
    data = sc.textFile('data/ratings.txt')
    data.first()

    data_sep = data.map(lambda l: l.split(','))
    data_sep.first()

    ratings = data_sep.map(lambda l: Rating(int(l[0]), int(l[1]), float(l[2])))
    ratings.first()

    return ratings


def build_ALS_model(ratings):
    # Build the recommendation model using Alternating Least Squares
    rank = 10
    numIterations = 20
    model = ALS.train(ratings, rank, numIterations)

    return model


def evaluate_train_data(model, ratings):

    # Evaluate the model on training data
    testdata = ratings.map(lambda p: (p[0], p[1]))
    testdata.first()

    predictions = model.predictAll(testdata).map(lambda r: ((r[0], r[1]), r[2]))
    predictions.first()

    ratesAndPreds = ratings.map(lambda r: ((r[0], r[1]), r[2])).join(predictions)
    ratesAndPreds.first()

    MSE = ratesAndPreds.map(lambda r: (r[1][0] - r[1][1]) ** 2).mean()
    print("Mean Squared Error = " + str(MSE))

    return ratesAndPreds


def one_prediction(model, user=None, n=10):
    if user is None:
        ratings = get_ratings_contents()
        avg_ratings = ratings.groupby('game').mean()['score']
        top_games = avg_ratings.argsort()[: -(n + 1): -1]
        return top_games

    predictions = model.recommendProducts(user, n)
    top_games = [line[1] for line in predictions]
    return top_games

def top_10_games_all_users(data_sep, model, n=10, save_pickle=False):
    users = data_sep.map(lambda l: int(l[1])).distinct().collect()
    top_games = defaultdict(list)

    ratings = get_ratings_contents()
    avg_ratings = ratings.groupby('game').mean()['score']
    all_users = avg_ratings.argsort()[: -(n + 1): -1].tolist()

    top_games['all_users'] = all_users
    
    for user in users:
        top_10 = model.recommendProducts(user, n)
        for each in top_10:
            user = each[0]
            game = each[1]
            top_games[user].append(game)

    if save_pickle:
        with open('data/top_games.pkl', 'wb') as f:
            pickle.dump(top_games, f)



