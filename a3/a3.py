# coding: utf-8

# # Assignment 3:  Recommendation systems
#
# Here we'll implement a content-based recommendation algorithm.
# It will use the list of genres for a movie as the content.
# The data come from the MovieLens project: http://grouplens.org/datasets/movielens/
# Note that I have not provided many doctests for this one. I strongly
# recommend that you write your own for each function to ensure your
# implementation is correct.

# Please only use these imports.
from collections import Counter, defaultdict
import math
import numpy as np
import os
import pandas as pd
import re
from scipy.sparse import csr_matrix
import urllib.request
import zipfile

def download_data():
    """ DONE. Download and unzip data.
    """
    url = 'https://www.dropbox.com/s/p9wmkvbqt1xr6lc/ml-latest-small.zip?dl=1'
    urllib.request.urlretrieve(url, 'ml-latest-small.zip')
    zfile = zipfile.ZipFile('ml-latest-small.zip')
    zfile.extractall()
    zfile.close()


def tokenize_string(my_string):
    """ DONE. You should use this in your tokenize function.
    """
    return re.findall('[\w\-]+', my_string.lower())


def tokenize(movies):
    """
    Append a new column to the movies DataFrame with header 'tokens'.
    This will contain a list of strings, one per token, extracted
    from the 'genre' field of each movie. Use the tokenize_string method above.

    Note: you may modify the movies parameter directly; no need to make
    a new copy.
    Params:
      movies...The movies DataFrame
    Returns:
      The movies DataFrame, augmented to include a new column called 'tokens'.

    >>> movies = pd.DataFrame([[123, 'Horror|Romance'], [456, 'Sci-Fi']], columns=['movieId', 'genres'])
    >>> movies = tokenize(movies)
    >>> movies['tokens'].tolist()
    [['horror', 'romance'], ['sci-fi']]
    """
    columnVals =[]
    for index, row in movies.iterrows():
        tokens = tokenize_string(str(row.genres))
        columnVals.append(tokens)

    tokenPd = pd.DataFrame({'tokens': columnVals})
    movies = movies.join(tokenPd)
    return movies


def featurize(movies):
    """
    Append a new column to the movies DataFrame with header 'features'.
    Each row will contain a csr_matrix of shape (1, num_features). Each
    entry in this matrix will contain the tf-idf value of the term, as
    defined in class:
    tfidf(i, d) := tf(i, d) / max_k tf(k, d) * log10(N/df(i))
    where:
    i is a term
    d is a document (movie)
    tf(i, d) is the frequency of term i in document d
    max_k tf(k, d) is the maximum frequency of any term in document d
    N is the number of documents (movies)
    df(i) is the number of unique documents containing term i

    Params:
      movies...The movies DataFrame
    Returns:
      A tuple containing:
      - The movies DataFrame, which has been modified to include a column named 'features'.
      - The vocab, a dict from term to int. Make sure the vocab is sorted alphabetically as in a2 (e.g., {'aardvark': 0, 'boy': 1, ...})

    >>> movies = pd.DataFrame([[123, 'Horror|Romance'], [456, 'Sci-Fi|Horror']], columns=['movieId', 'genres'])
    >>> movies, vocab = featurize(movies)
    >>> vocab
    {'horror': 0, 'romance': 1, 'sci-fi': 2}
    >>> movies['features'][0].toarray()
    array([[0.     , 0.30103, 0.     ]])
    >>> movies['features'][1].toarray()
    array([[0.     , 0.     , 0.30103]])
    """
    termSet = set()
    for index, row in movies.iterrows():
        for term in list(row.tokens):
            termSet.add(term)

    vocab = {word: index for index, word in enumerate(sorted(list(termSet)))}
    tf = defaultdict(lambda: defaultdict(lambda: 0.0)) # term i + doc d -> freq of i in d
    df = defaultdict(lambda: 0.0) # term i -> #docs that contains term i
    maxtf = defaultdict(lambda: 0.0) # doc d -> max_k{tf[k][d]}

    for d, movie in movies.iterrows():
        for term in list(movie.tokens):
            tf[vocab[term]][d] += 1.0
            maxtf[d] = max(maxtf[d], tf[vocab[term]][d])

        for term in list(set(movie.tokens)):
            df[vocab[term]] += 1.0

    columnVals = []
    for d, movie in movies.iterrows():
        values, colIndices = [], []
        for term in list(set(movie.tokens)):
            i = vocab[term]
            tfidf = tf[i][d] / maxtf[d] * math.log10(movies.shape[0] / df[i])
            values.append(tfidf)
            colIndices.append(i)

        csrFeatures = csr_matrix((values, ([0] * len(values), colIndices)),
                                 shape=(1, len(vocab)))
        columnVals.append(csrFeatures)

    featurePd = pd.DataFrame({'features': columnVals})
    movies = movies.join(featurePd)
    return movies, vocab


def train_test_split(ratings):
    """DONE.
    Returns a random split of the ratings matrix into a training and testing set.
    """
    test = set(range(len(ratings))[::1000])
    train = sorted(set(range(len(ratings))) - test)
    test = sorted(test)
    return ratings.iloc[train], ratings.iloc[test]


def cosine_sim(a, b):
    """
    Compute the cosine similarity between two 1-d csr_matrices.
    Each matrix represents the tf-idf feature vector of a movie.
    Params:
      a...A csr_matrix with shape (1, number_features)
      b...A csr_matrix with shape (1, number_features)
    Returns:
      A float. The cosine similarity, defined as: dot(a, b) / ||a|| * ||b||
      where ||a|| indicates the Euclidean norm (aka L2 norm) of vector a.
    >>> a = csr_matrix([0., 0., 3., 0., 4.], shape=(1, 5))
    >>> b = csr_matrix([0., 0., 3., 4., 0.], shape=(1, 5))
    >>> cosine_sim(a, b)
    0.36
    """
    def norm(a):
        return np.sqrt(a.multiply(a).sum())

    return a.dot(b.transpose()).sum() / (norm(a) * norm(b))


def make_predictions(movies, ratings_train, ratings_test):
    """
    Using the ratings in ratings_train, predict the ratings for each
    row in ratings_test.

    To predict the rating of user u for movie i: Compute the weighted average
    rating for every other movie that u has rated.  Restrict this weighted
    average to movies that have a positive cosine similarity with movie
    i. The weight for movie m corresponds to the cosine similarity between m
    and i.

    If there are no other movies with positive cosine similarity to use in the
    prediction, use the mean rating of the target user in ratings_train as the
    prediction.

    Params:
      movies..........The movies DataFrame.
      ratings_train...The subset of ratings used for making predictions. These are the "historical" data.
      ratings_test....The subset of ratings that need to predicted. These are the "future" data.
    Returns:
      A numpy array containing one predicted rating for each element of ratings_test.
    """
    predictions = []
    train_movies = ratings_train.join(movies, on='movieId', how='inner',
                                      lsuffix='_rating', rsuffix='_movie')
    for _, row in ratings_test.iterrows():
        uid, mid = int(row.userId), int(row.movieId)
        unratedMovie = movies[movies.movieId == mid]
        ratedMovies = train_movies[train_movies.userId == uid]
        rating, totalSim = 0.0, 0.0
        for _, movie in ratedMovies.iterrows():
            sim = cosine_sim(movie.features, list(unratedMovie.features)[0])
            if sim > 0:
                rating += sim * movie.rating
                totalSim += sim

        if totalSim == 0.0:
            rating = np.mean(ratedMovies.rating)
            print('Fallback to average rating = %.2f' % rating)
        else:
            rating /= totalSim
            # print('Weighted over similarity rating = %.2f' % rating)

        predictions.append(rating)

    return np.array(predictions)


def mean_absolute_error(predictions, ratings_test):
    """DONE.
    Return the mean absolute error of the predictions.
    """
    return np.abs(predictions - np.array(ratings_test.rating)).mean()


def main():
    download_data()
    path = 'ml-latest-small'
    ratings = pd.read_csv(path + os.path.sep + 'ratings.csv')
    movies = pd.read_csv(path + os.path.sep + 'movies.csv')
    movies = tokenize(movies)
    movies, vocab = featurize(movies)
    print(movies[:5])
    print(ratings[:5])
    print('vocab (size=%d):' % len(vocab))
    print(sorted(vocab.items())[:10])
    ratings_train, ratings_test = train_test_split(ratings)
    print('%d training ratings; %d testing ratings' % (len(ratings_train), len(ratings_test)))
    predictions = make_predictions(movies, ratings_train, ratings_test)
    print('error=%f' % mean_absolute_error(predictions, ratings_test))
    print(predictions[:10])
    print(ratings_test.rating[:10])


if __name__ == '__main__':
    main()
