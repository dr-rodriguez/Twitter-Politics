from nltk.corpus import stopwords
from nltk.tokenize import wordpunct_tokenize
from nltk.stem.porter import PorterStemmer
from collections import Counter
import string
import pandas as pd
import numpy as np
from sklearn.externals import joblib
from sklearn.decomposition import PCA
from sklearn.metrics import confusion_matrix, classification_report
from sklearn.cross_validation import train_test_split
from sklearn import svm, grid_search
import matplotlib.pyplot as plt
from math import sqrt
import seaborn as sns

# Set style for seaborn
sns.set_style('whitegrid')

# TODO: Look into adding some form of sentiment analysis
class Analyzer:
    """
    Class for carrying out the analysis and model creation/loading
    """

    def __init__(self, data, labels=None, max_words=150, load_pca=False, load_svm=False, more_stop_words=[''],
                 use_sentiment=True):
        self.data = data  # Data matrix
        self.labels = labels  # Label array

        # Text Mining
        self.max_words = max_words
        self.dtm = []
        self.top_words = dict()
        self.words = Counter()
        self.more_stop_words = more_stop_words

        # Principal Component Analysis
        self.load_pca = load_pca  # Load or compute the PCA?
        self.pca = None
        self.pcscores = None
        self.loadings = None
        self.load_squared = None

        # Sentiment analysis
        self.sentiment = None
        self.use_sentiment = use_sentiment

        # Support Vector Machine Classifier
        self.load_svm = load_svm
        self.svc = None

        # Use stemming
        self.porter = PorterStemmer()

        # Set stop words
        self.stop_words = set(stopwords.words('english'))
        self.stop_words.update([s for s in string.punctuation] +
                               [u'\u2014', u'\u2019', u'\u201c', u'\xf3', u'\u201d', u'\u2014@', u'://', u'!"', u'"@',
                                u'."', u'.@', u'co', u'\u2026', u'&', u'&amp', u'amp', u'...', u'.\u201d', u'000',
                                u'\xed'])

        # Political terms and Twitter handles to remove
        self.stop_words.update(['hillary', 'clinton', 'donald', 'trump', 'clinton2016',
                                'trump2016', 'hillary2016', 'makeamericagreatagain'])
        self.stop_words.update(['realdonaldtrump', 'hillaryclinton', 'berniesanders'])
        self.stop_words.update(self.more_stop_words)

    def create_full_model(self):
        print('Getting top {} words...'.format(self.max_words))
        self.get_words()
        print('Creating document term matrix...')
        self.create_dtm()
        print('Running Principal Component Analysis...')
        self.run_pca()
        if self.use_sentiment:
            print('Running Sentiment Analysis...')
            self.get_sentiment()
        print('Running Support Vector Machine Classifier...')
        return self.run_svm()

    def load_full_model(self):
        self.load_words()
        self.create_dtm()
        self.run_pca()
        if self.use_sentiment: self.get_sentiment()
        return self.run_svm()

    def get_words(self):
        str_list = ' '.join([tweet for tweet in self.data])

        self.words = Counter([self.porter.stem(i.lower()) for i in wordpunct_tokenize(str_list)
                         if i.lower() not in self.stop_words and not i.lower().startswith('http')])
        self.top_words = dict(self.words.most_common(self.max_words))

    def save_words(self, filename='words.pkl'):
        joblib.dump(self.top_words, 'model/'+filename)

    def load_words(self, filename='words.pkl'):
        print('Loading model/{}'.format(filename))
        self.top_words = joblib.load('model/'+filename)

    def create_dtm(self):
        dtm = []
        for tweet in self.data:

            # Make empty row
            newrow = dict()
            for term in self.top_words.keys():
                newrow[term] = 0

            tweetwords = [self.porter.stem(i.lower()) for i in wordpunct_tokenize(tweet)
                          if i.lower() not in self.stop_words and not i.lower().startswith('http')]

            for word in tweetwords:
                if word in self.top_words.keys():
                    newrow[word] += 1

            dtm.append(newrow)

        self.dtm = dtm

    def get_sentiment(self):
        # Load up the NRC emotion lexicon
        filename = 'data/NRC-emotion-lexicon-wordlevel-alphabetized-v0.92.txt'

        data = pd.read_csv(filename, delim_whitespace=True, skiprows=45, header=None, names=['word', 'affect', 'flag'])

        emotion_words = dict()
        emotion_map = dict()
        affects = ['positive', 'negative', 'anger', 'anticipation', 'disgust',
                   'fear', 'joy', 'sadness', 'surprise', 'trust']
        for key in affects:
            emotion_words[key] = data[(data['affect'] == key) & (data['flag'] == 1)]['word'].tolist()
            emotion_map[key] = list()

        for text in self.data:  # Note no stemming or it may fail to match words
            words = Counter([i.lower() for i in wordpunct_tokenize(text)
                         if i.lower() not in self.stop_words and not i.lower().startswith('http')])
            for key in emotion_words.keys():
                x = set(emotion_words[key]).intersection(words.keys())
                emotion_map[key].append(len(x))
        self.sentiment = pd.DataFrame(emotion_map)

    def run_pca(self, filename='pca.pkl'):
        df_dtm = pd.DataFrame(self.dtm, columns=self.top_words.keys())

        # Load or run the PCA
        if self.load_pca:
            print('Loading model/{}'.format(filename))
            pca = joblib.load('model/'+filename)
        else:
            pca = PCA(n_components=0.8)
            pca.fit(df_dtm)

        pcscores = pd.DataFrame(pca.transform(df_dtm))
        pcscores.columns = ['PC' + str(i + 1) for i in range(pcscores.shape[1])]
        loadings = pd.DataFrame(pca.components_, columns=self.top_words.keys())
        load_squared = loadings.transpose() ** 2
        load_squared.columns = ['PC' + str(i + 1) for i in range(pcscores.shape[1])]

        self.pcscores = pcscores
        self.loadings = loadings
        self.load_squared = load_squared

        # Prep for save, just in case
        self.pca = pca

    def save_pca(self, filename='pca.pkl'):
        joblib.dump(self.pca, 'model/' + filename)

    def run_svm(self, filename='svm.pkl'):
        if not self.load_svm:
            if self.use_sentiment:
                self.pcscores.index = range(len(self.pcscores))
                data = pd.concat([self.pcscores, self.sentiment], axis=1)
            else:
                data = self.pcscores
            df_train, df_test, train_label, test_label = train_test_split(data, self.labels,
                                                                          test_size=0.2, random_state=42)
            parameters = {'kernel': ['rbf'], 'C': [0.01, 0.1, 1, 10, 100], 'gamma': [1e-3, 1e-2, 1e-1, 1e0, 1e1]}
            svr = svm.SVC()
            clf = grid_search.GridSearchCV(svr, parameters, cv=5, error_score=0, verbose=1)
            clf.fit(df_train, train_label)
            print('Best parameters: {}'.format(clf.best_params_))
            prediction = clf.predict(df_test)
            self.svc = clf
            return prediction, test_label
        else:
            print('Loading model/{}'.format(filename))
            clf = joblib.load('model/'+filename)
            if self.use_sentiment:
                self.pcscores.index = range(len(self.pcscores))
                data = pd.concat([self.pcscores, self.sentiment], axis=1)
            else:
                data = self.pcscores
            prediction = clf.predict(data)
            self.svc = clf
            return prediction

    def save_svm(self, filename='svm.pkl'):
        joblib.dump(self.svc, 'model/' + filename)

    def make_confusion_matrix(self, test_label, test_predict, normalize=False, axis=0, label_names=['Hillary', 'Trump']):
        cm = confusion_matrix(test_label, test_predict)
        if normalize:
            cm = cm.astype('float') / cm.sum(axis=axis)[:, np.newaxis]

        pretty_cm(cm)
        print(classification_report(test_label, test_predict, target_names=label_names))

        return cm

    def make_biplot(self, xval=0, yval=1, max_arrow=0.2, save=False, alpha=0.4, use_sns=False):
        """
        Create a biplot of the PCA components

        :param xval: PCA component for the x-axis
        :param yval: PCA component for the y-axis
        :param max_arrow: Scaling to control how many arrows are plotted
        :param save: Filename or False if no save needed
        :param alpha: Transparency
        :return:
        """

        # Check if pca has been run
        if self.pcscores is None:
            print('Run PCA first')
            return

        n = self.loadings.shape[1]
        scalex = 1.0 / (self.pcscores.iloc[:, xval].max() - self.pcscores.iloc[:, xval].min())  # Rescaling to be from -1 to +1
        scaley = 1.0 / (self.pcscores.iloc[:, yval].max() - self.pcscores.iloc[:, yval].min())

        if use_sns:
            # Use seaborn
            cut = 120
            g = sns.JointGrid(x=self.pcscores.iloc[:, xval][self.labels == 0] * scalex,
                              y=self.pcscores.iloc[:, yval][self.labels == 0] * scaley)
            g.plot_joint(plt.scatter, c='blue', label='Hillary Clinton', alpha=alpha)
            g.plot_marginals(sns.kdeplot, shade=True, color='blue', cut=cut)
            # g.plot_marginals(sns.distplot, color='blue')

            g.x = self.pcscores.iloc[:, xval][self.labels == 1] * scalex
            g.y = self.pcscores.iloc[:, yval][self.labels == 1] * scaley
            g.plot_joint(plt.scatter, c='red', label='Donald Trump', alpha=alpha)
            plt.legend(loc='best')
            g.plot_marginals(sns.kdeplot, shade=True, color='red', legend=False, cut=cut)
            # g.plot_marginals(sns.distplot, color='red')

            g.x, g.y = [], []
            g.plot_joint(plt.scatter)

            # Draw arrows
            for i in range(n):
                # Only plot the longer ones
                length = sqrt(self.loadings.iloc[xval, i] ** 2 + self.loadings.iloc[yval, i] ** 2)
                if length < max_arrow:
                    continue

                plt.arrow(0, 0, self.loadings.iloc[xval, i], self.loadings.iloc[yval, i], color='g', alpha=0.9)
                plt.text(self.loadings.iloc[xval, i] * 1.15, self.loadings.iloc[yval, i] * 1.15,
                         self.loadings.columns.tolist()[i], color='k', ha='center', va='center')

            plt.xlim(-1, 1)
            plt.ylim(-1, 1)
            plt.xlabel('PC{}'.format(xval + 1))
            plt.ylabel('PC{}'.format(yval + 1))
            if save: g.savefig(save)
            plt.show()
        else:
            plt.figure()
            if self.labels is not None:
                plt.plot(self.pcscores.iloc[:, xval][self.labels == 0] * scalex, self.pcscores.iloc[:, yval][self.labels == 0] * scaley,
                         'bo', alpha=alpha, label='Hillary Clinton')
                plt.plot(self.pcscores.iloc[:, xval][self.labels == 1] * scalex, self.pcscores.iloc[:, yval][self.labels == 1] * scaley,
                         'ro', alpha=alpha, label='Donald Trump')
            else:
                plt.plot(self.pcscores.iloc[:, xval] * scalex, self.pcscores.iloc[:, yval] * scaley,
                         'bo', alpha=alpha)

            for i in range(n):
                # Only plot the longer ones
                length = sqrt(self.loadings.iloc[xval, i]**2 + self.loadings.iloc[yval, i]**2)
                if length < max_arrow:
                    continue

                plt.arrow(0, 0, self.loadings.iloc[xval, i], self.loadings.iloc[yval, i], color='g', alpha=0.9)
                plt.text(self.loadings.iloc[xval, i] * 1.15, self.loadings.iloc[yval, i] * 1.15,
                         self.loadings.columns.tolist()[i], color='k', ha='center', va='center')

            plt.xlim(-1, 1)
            plt.ylim(-1, 1)
            plt.xlabel('PC{}'.format(xval+1))
            plt.ylabel('PC{}'.format(yval+1))
            if self.labels is not None: plt.legend(loc='best', numpoints=1)
            plt.grid()
            if save: plt.savefig(save)
            plt.show()


def pretty_cm(cm, label_names=['Hillary', 'Trump'], show_sum=False):
    table = pd.DataFrame(cm, columns=['P-' + s for s in label_names], index=['T-' + s for s in label_names])
    print(table)
    if show_sum:
        print('Sum of columns: {}'.format(cm.sum(axis=0)))
        print('Sum of rows: {}'.format(cm.sum(axis=1)))
    print('')

