#!/usr/bin/env python3
# 601.465/665 - Natural Language Processing
# Assignment 6 - HMM
# Author: Amir Hussein

from __future__ import annotations

import logging
import sys

from pathlib import Path
import pdb
import torch
from torch import nn
from torch import optim
from typing import Counter
from collections import Counter
import random
import numpy as np
from tqdm import trange
import tqdm
import math


log = logging.getLogger(Path(__file__).stem)  # Basically the only okay global variable.

##### TYPE DEFINITIONS (USED FOR TYPE ANNOTATIONS)
from typing import Iterable, List, Optional, Set, Tuple, Union

Wordtype = str  # if you decide to integerize the word types, then change this to int
Vocab    = Set[Wordtype]
Zerogram = Tuple[()]
Unigram  = Tuple[Wordtype]
Bigram   = Tuple[Wordtype, Wordtype]
Trigram  = Tuple[Wordtype, Wordtype, Wordtype]
Ngram    = Union[Zerogram, Unigram, Bigram, Trigram]
Vector   = List[float]


##### CONSTANTS
BOS: Wordtype = "BOS"  # special word type for context at Beginning Of Sequence
EOS: Wordtype = "EOS"  # special word type for observed token at End Of Sequence
OOV: Wordtype = "OOV"  # special word type for all Out-Of-Vocabulary words
OOL: Wordtype = "OOL"  # special word type whose embedding is used for OOV and all other Out-Of-Lexicon words

##### read lexicon class
class Lexicon:
	"""
    Class that manages a lexicon and can compute similarity.
    >>> my_lexicon = Lexicon.from_file(my_file)
	>>> my_lexicon.find_similar_words(bagpipe)
	"""

	def __init__(self, int_to_word={},word_to_int={},embeddings=None) -> None:
		"""Load information into coupled word-index mapping and embedding matrix."""
		# FINISH THIS FUNCTION
		self.word_to_int = word_to_int
		self.int_to_word = int_to_word
		self.embeddings = embeddings
        # Store your stuff! Both the word-index mapping and the embedding matrix.
        #
        # Do something with this size info?
        # PyTorch's th.Tensor objects rely on fixed-size arrays in memory.
        # One of the worst things you can do for efficiency is
        # append row-by-row, like you would with a Python list.
        #
        # Probably make the entire list all at once, then convert to a th.Tensor.
        # Otherwise, make the th.Tensor and overwrite its contents row-by-row.

	@classmethod
	def from_file(cls, file: Path) -> Lexicon:
        # FINISH THIS FUNCTION
		lines = []
		count = 0
		word_to_int = {}
		int_to_word={}
		
		with open(file) as f:
			first_line = next(f)  # Peel off the special first line.
			for line in f:  # All of the other lines are regular.
                  # `pass` is a placeholder. Replace with real code!
				line = line.split('\t')
				lines.append(np.array(line[1:],dtype=np.float64))
				int_to_word[count]=line[0]
				word_to_int[line[0]]=count
				count+=1
		embeddings = torch.tensor(lines, dtype=torch.float64)
		lexicon = Lexicon(int_to_word,word_to_int, embeddings)  # Maybe put args here. Maybe follow Builder pattern
		return lexicon



##### UTILITY FUNCTIONS FOR CORPUS TOKENIZATION

def read_tokens(file: Path, vocab: Optional[Vocab] = None) -> Iterable[Wordtype]:
    """Iterator over the tokens in file.  Tokens are whitespace-delimited.
    If vocab is given, then tokens that are not in vocab are replaced with OOV."""

    # OPTIONAL SPEEDUP: You may want to modify this to integerize the
    # tokens, using integerizer.py as in previous homeworks.
    # In that case, redefine `Wordtype` from `str` to `int`.

    # PYTHON NOTE: This function uses `yield` to return the tokens one at
    # a time, rather than constructing the whole sequence and using
    # `return` to return it.
    #
    # A function that uses `yield` is called a "generator."  As with other
    # iterators, it computes new values only as needed.  The sequence is
    # never fully constructed as an single object in memory.
    #
    # You can iterate over the yielded sequence, for example, like this:
    #      for token in read_tokens(my_file, vocab):
    #          process_the_token(token)
    # Whenever the `for` loop needs another token, read_tokens picks up where it
    # left off and continues running until the next `yield` statement.

    with open(file) as f:
        for line in f:
            for token in line.split():
                if vocab is None or token in vocab:
                    yield token
                else:
                    yield OOV  # replace this out-of-vocabulary word with OOV
            yield EOS  # Every line in the file implicitly ends with EOS.


def num_tokens(file: Path) -> int:
    """Give the number of tokens in file, including EOS."""
    return sum(1 for _ in read_tokens(file))


def read_trigrams(file: Path, vocab: Vocab) -> Iterable[Trigram]:
    """Iterator over the trigrams in file.  Each triple (x,y,z) is a token z
    (possibly EOS) with a left context (x,y)."""
    x, y = BOS, BOS
    for z in read_tokens(file, vocab):
        yield (x, y, z)
        if z == EOS:
            x, y = BOS, BOS  # reset for the next sequence in the file (if any)
        else:
            x, y = y, z  # shift over by one position.


def draw_trigrams_forever(file: Path, 
                          vocab: Vocab, 
                          randomize: bool = False) -> Iterable[Trigram]:
    """Infinite iterator over trigrams drawn from file.  We iterate over
    all the trigrams, then do it again ad infinitum.  This is useful for 
    SGD training.  
    
    If randomize is True, then randomize the order of the trigrams each time.  
    This is more in the spirit of SGD, but the randomness makes the code harder to debug, 
    and forces us to keep all the trigrams in memory at once.
    """
    trigrams = read_trigrams(file, vocab)
    if not randomize:
        import itertools
        return itertools.cycle(trigrams)  # repeat forever
    else:
        import random
        pool = tuple(trigrams)   
        while True:
            for trigram in random.sample(pool, len(pool)):
                yield trigram

##### READ IN A VOCABULARY (e.g., from a file created by build_vocab.py)

def read_vocab(vocab_file: Path) -> Vocab:
    vocab: Vocab = set()
    with open(vocab_file, "rt") as f:
        for line in f:
            word = line.strip()
            vocab.add(word)
    log.info(f"Read vocab of size {len(vocab)} from {vocab_file}")
    return vocab

##### LANGUAGE MODEL PARENT CLASS

class LanguageModel:

    def __init__(self, vocab: Vocab):
        super().__init__()

        self.vocab = vocab
        self.progress = 0   # To print progress.

        self.event_count:   Counter[Ngram] = Counter()  # numerator c(...) function.
        self.context_count: Counter[Ngram] = Counter()  # denominator c(...) function.
        # In this program, the argument to the counter should be an Ngram, 
        # which is always a tuple of Wordtypes, never a single Wordtype:
        # Zerogram: context_count[()]
        # Bigram:   context_count[(x,y)]   or equivalently context_count[x,y]
        # Unigram:  context_count[(y,)]    or equivalently context_count[y,]
        # but not:  context_count[(y)]     or equivalently context_count[y]  
        #             which incorrectly looks up a Wordtype instead of a 1-tuple

    @property
    def vocab_size(self) -> int:
        assert self.vocab is not None
        return len(self.vocab)

    # We need to collect two kinds of n-gram counts.
    # To compute p(z | xy) for a trigram xyz, we need c(xy) for the 
    # denominator and c(yz) for the backed-off numerator.  Both of these 
    # look like bigram counts ... but they are not quite the same thing!
    #
    # For a sentence of length N, we are iterating over trigrams xyz where
    # the position of z falls in 1 ... N+1 (so z can be EOS but not BOS),
    # and therefore
    # the position of y falls in 0 ... N   (so y can be BOS but not EOS).
    # 
    # When we write c(yz), we are counting *events z* with *context* y:
    #         c(yz) = |{i in [1, N]: w[i-1] w[i] = yz}|
    # We keep these "event counts" in `event_count` and use them in the numerator.
    # Notice that z=BOS is not possible (BOS is not a possible event).
    # 
    # When we write c(xy), we are counting *all events* with *context* xy:
    #         c(xy) = |{i in [1, N]: w[i-2] w[i-1] = xy}|
    # We keep these "context counts" in `context_count` and use them in the denominator.
    # Notice that y=EOS is not possible (EOS cannot appear in the context).
    #
    # In short, c(xy) and c(yz) count the training bigrams slightly differently.  
    # Likewise, c(y) and c(z) count the training unigrams slightly differently.
    #
    # Note: For bigrams and unigrams that don't include BOS or EOS -- which
    # is most of them! -- `event_count` and `context_count` will give the
    # same value.  So you could save about half the memory if you were
    # careful to store those cases only once.  (How?)  That would make the
    # code slightly more complicated, but would be worth it in a real system.

    def count_trigram_events(self, trigram: Trigram) -> None:
        """Record one token of the trigram and also of its suffixes (for backoff)."""
        (x, y, z) = trigram
        self.event_count[(x, y, z )] += 1
        self.event_count[   (y, z )] += 1
        self.event_count[      (z,)] += 1  # the comma is necessary to make this a tuple
        self.event_count[        ()] += 1

    def count_trigram_contexts(self, trigram: Trigram) -> None:
        """Record one token of the trigram's CONTEXT portion, 
        and also the suffixes of that context (for backoff)."""
        (x, y, _) = trigram    # we don't care about z
        self.context_count[(x, y )] += 1
        self.context_count[   (y,)] += 1
        self.context_count[     ()] += 1

    def prob(self, x: Wordtype, y: Wordtype, z: Wordtype) -> float:
        """Computes a smoothed estimate of the trigram probability p(z | x,y)
        according to the language model.
        """
        class_name = type(self).__name__
        if class_name == LanguageModel.__name__:
            raise NotImplementedError("You shouldn't be calling prob on an instance of LanguageModel, but on an instance of one of its subclasses.")
        raise NotImplementedError(
            f"{class_name}.prob is not implemented yet (you should override LanguageModel.prob)"
        )

    @classmethod
    def load(cls, source: Path) -> "LanguageModel":
        import pickle  # for loading/saving Python objects
        log.info(f"Loading model from {source}")
        with open(source, mode="rb") as f:
            log.info(f"Loaded model from {source}")
            return pickle.load(f)

    def sample(self,max_length=20, start_symbol='BOS', end_symbol='EOS'):
    #     """ implementation od sampling method Q6
    #      Args:
                               
    #         max_length (int): max number of words in a generated sentence
        
    #     Returns:
    #         gen_sen: the generated random sentence 
        
    #     """
        self.gen_sen = ""
        x , y = "BOS", "BOS"
        #pdb.set_trace()
        self.new_sample((x,y), self.gen_sen, max_length)
   
    def new_sample(self, context, gen_sen, remaining_expansions):
        remaining_expansions -= 1
        probs = []
        choice_opt = []
        x,y = context
        for z in self.vocab:
            probs.append(self.prob(x,y,z))
            choice_opt.append(z)
        sample =  random.choices(choice_opt, weights=probs, k=1)[0]
        if sample == "":
            pass
        else:
            self.gen_sen = self.gen_sen + " " + sample
            if len(gen_sen) > 0 and gen_sen[-1] == "EOS":
                return 
                #gen_sen = gen_sen + "(" + node.name + " "
            elif remaining_expansions == 0 and gen_sen[-1] != "EOS":
                    self.gen_sen += " ..."
                    return
            else:
                x, y = y, z 
        self.new_sample((x,y), self.gen_sen, remaining_expansions)
    
    def save(self, destination: Path) -> None:
        import pickle
        log.info(f"Saving model to {destination}")
        with open(destination, mode="wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)
        log.info(f"Saved model to {destination}")

    def train(self, file: Path) -> None:
        """Create vocabulary and store n-gram counts.  In subclasses, we might
        override this with a method that computes parameters instead of counts."""

        log.info(f"Training from corpus {file}")

        # Clear out any previous training.
        self.event_count   = Counter()
        self.context_count = Counter()

        for trigram in read_trigrams(file, self.vocab):
            self.count_trigram_events(trigram)
            self.count_trigram_contexts(trigram)
            self.show_progress()

        sys.stderr.write("\n")  # done printing progress dots "...."
        log.info(f"Finished counting {self.event_count[()]} tokens")

    def show_progress(self, freq: int = 5000) -> None:
        """Print a dot to stderr every 5000 calls (frequency can be changed)."""
        self.progress += 1
        if self.progress % freq == 1:
            sys.stderr.write(".")


##### SPECIFIC FAMILIES OF LANGUAGE MODELS

class UniformLanguageModel(LanguageModel):
    def prob(self, x: Wordtype, y: Wordtype, z: Wordtype) -> float:
        return 1 / self.vocab_size


class AddLambdaLanguageModel(LanguageModel):
    def __init__(self, vocab: Vocab, lambda_: float) -> None:
        super().__init__(vocab)

        if lambda_ < 0:
            raise ValueError("negative lambda argument of {lambda_}")
        self.lambda_ = lambda_

    def prob(self, x: Wordtype, y: Wordtype, z: Wordtype) -> float:
        assert self.event_count[x, y, z] <= self.context_count[x, y]
        return ((self.event_count[x, y, z] + self.lambda_) / 
                (self.context_count[x, y] + self.lambda_ * self.vocab_size))

        # Notice that summing the numerator over all values of typeZ
        # will give the denominator.  Therefore, summing up the quotient
        # over all values of typeZ will give 1, so sum_z p(z | ...) = 1
        # as is required for any probability function.


class BackoffAddLambdaLanguageModel(AddLambdaLanguageModel):
    def __init__(self, vocab: Vocab, lambda_: float) -> None:
        super().__init__(vocab, lambda_)

    def prob(self, x: Wordtype, y: Wordtype, z: Wordtype) -> float:
        # TODO: Reimplement me so that I do backoff
        assert self.event_count[x, y, z] <= self.context_count[x, y]
        #pdb.set_trace()
        # p_unigrams = self.event_count[(z,)]/self.context_count[()]
        p_unigrams = (self.event_count[(z,)]+self.lambda_)/(self.context_count[()]+self.lambda_*self.vocab_size)
        if p_unigrams ==0:
            p_unigrams = self.event_count[('OOV',)]/self.context_count[()]
            p_bigrams = (self.event_count[(y,'OOV')] + self.lambda_*self.vocab_size*p_unigrams)/(self.context_count[(y,)]+self.lambda_*self.vocab_size)
            
            trigram = ((self.event_count[x, y, 'OOV'] + self.lambda_*self.vocab_size*p_bigrams) /
                    (self.context_count[x, y] + self.lambda_ * self.vocab_size))
        else:
            p_bigrams = (self.event_count[(y,z)] + self.lambda_*self.vocab_size*p_unigrams)/(self.context_count[(y,)]+self.lambda_*self.vocab_size)
            
            trigram = ((self.event_count[x, y, z] + self.lambda_*self.vocab_size*p_bigrams) /
                    (self.context_count[x, y] + self.lambda_ * self.vocab_size))
       # if trigram <= 0.0:
        #     pdb.set_trace()
        return trigram
        #return super().prob(x, y, z)
        # Don't forget the difference between the Wordtype z and the
        # 1-element tuple (z,). If you're looking up counts,
        # these will have very different counts!


class EmbeddingLogLinearLanguageModel(LanguageModel, nn.Module):
    # Note the use of multiple inheritance: we are both a LanguageModel and a torch.nn.Module.
    
    def __init__(self, vocab: Vocab, lexicon_file: Path, l2: float) -> None:
        super().__init__(vocab)
        if l2 < 0:
            log.error(f"l2 regularization strength value was {l2}")
            raise ValueError("You must include a non-negative regularization value")
        self.l2: float = l2
        self.Z_den = None
        
        # TODO: READ THE LEXICON OF WORD VECTORS AND STORE IT IN A USEFUL FORMAT.
        self.lexicon = Lexicon.from_file(lexicon_file)
        
        self.dim =  len(self.lexicon.embeddings[1]) #99999999999  # TODO: SET THIS TO THE DIMENSIONALITY OF THE VECTORS
        self.vocab_emb = torch.zeros((len(self.vocab),self.dim),dtype=torch.float32)
        count = 0
        for word in self.vocab:
            if word in self.lexicon.word_to_int.keys():
                #pdb.set_trace()
                self.vocab_emb[count,:] = self.lexicon.embeddings[self.lexicon.word_to_int[word]]
            else:
            
                self.vocab_emb[count,:] = self.lexicon.embeddings[self.lexicon.word_to_int["OOL"]]
            count +=1
        #self.vocab_emb = torch.tensor(vocab_list, dtype=torch.float64)
            
        # We wrap the following matrices in nn.Parameter objects.
        # This lets PyTorch know that these are parameters of the model
        # that should be listed in self.parameters() and will be
        # updated during training.
        #
        # We can also store other tensors in the model class,
        # like constant coefficients that shouldn't be altered by
        # training, but those wouldn't use nn.Parameter.
        self.X = nn.Parameter(torch.zeros((self.dim, self.dim),dtype=torch.float32), requires_grad=True)
        self.Y = nn.Parameter(torch.zeros((self.dim, self.dim),dtype=torch.float32), requires_grad=True)

    def prob(self, x: Wordtype, y: Wordtype, z: Wordtype) -> float:
        # This returns an ordinary float probability, using the
        # .item() method that extracts a number out of a Tensor.
        #pdb.set_trace()
        
        
        if (z =="OOV" or z not in self.lexicon.word_to_int.keys()):
            z = self.lexicon.embeddings[self.lexicon.word_to_int["OOL"]]
        else:
            z = self.lexicon.embeddings[self.lexicon.word_to_int[z]] 
        

    
        if (y=="OOV" or y not in self.lexicon.word_to_int.keys()):
            y = self.lexicon.embeddings[self.lexicon.word_to_int["OOL"]]
        else:
            y = self.lexicon.embeddings[self.lexicon.word_to_int[y]] 
        
     
       
        if (x=="OOV" or x not in self.lexicon.word_to_int.keys()):
            x = self.lexicon.embeddings[self.lexicon.word_to_int["OOL"]]
        else:
            x = self.lexicon.embeddings[self.lexicon.word_to_int[x]] 
        
        p = self.log_prob(x, y, z)
       # assert isinstance(p, float)  # checks that we'll adhere to the return type annotation, which is inherited from superclass
        return torch.exp(p) # please change this to p when training the model

    def log_prob(self, x: Wordtype, y: Wordtype, z: Wordtype) -> torch.Tensor:
        """Return log p(z | xy) according to this language model."""
        # TODO: IMPLEMENT ME!
        # Don't forget that you can create additional methods
        # that you think are useful, if you'd like.
        # It's cleaner than making this function massive.
        #
        # Be sure to use vectorization over the vocabulary to
        # compute the normalization constant Z, or this method
        # will be very slow.
        #
        # The operator `@` is a nice way to write matrix multiplication:
        # you can write J @ K as shorthand for torch.mul(J, K).
        # J @ K looks more like the usual math notation.
        #pdb.set_trace()
        x = x.double()
        y = y.double()
        z = x.double()
        Xmat = torch.matmul(x,self.X.double())
        Ymat =  torch.matmul(y,self.Y.double())
        # Z_den = torch.sum(torch.exp(torch.matmul(Xmat,torch.transpose(self.vocab_emb,0,1).double())
        #                      + torch.matmul(Ymat,torch.transpose(self.vocab_emb,0,1).double())))
        #if self.Z_den == None:
        Z_den = torch.logsumexp(torch.matmul(Xmat,torch.transpose(self.vocab_emb,0,1).double())
                                + torch.matmul(Ymat,torch.transpose(self.vocab_emb,0,1).double()),0)
        #else:
        #   Z_den = self.Z_den
        p_num = torch.exp(torch.matmul(Xmat,z) + torch.matmul(Ymat,z))
        p = torch.log(p_num) - Z_den
        #self.Z_den = Z_den
        
        return p

    def train(self, file: Path):    # type: ignore
        
        ### Technically this method shouldn't be called `train`,
        ### because this means it overrides not only `LanguageModel.train` (as desired)
        ### but also `nn.Module.train` (which has a different type). 
        ### However, we won't be trying to use the latter method.
        ### The `type: ignore` comment above tells the type checker to ignore this inconsistency.
        
        # Optimization hyperparameters.
        gamma0 = 0.1  # initial learning rate

        # This is why we needed the nn.Parameter above.
        # The optimizer needs to know the list of parameters
        # it should be trying to update.
        optimizer = optim.SGD(self.parameters(), lr=gamma0)

        # Initialize the parameter matrices to be full of zeros.
        nn.init.zeros_(self.X)   # type: ignore
        nn.init.zeros_(self.Y)   # type: ignore

        N = num_tokens(file)
        log.info("Start optimizing on {N} training tokens...")

        #####################
        # TODO: Implement your SGD here by taking gradient steps on a sequence
        # of training examples.  Here's how to use PyTorch to make it easy:
        #
        # To get the training examples, you can use the `read_trigrams` function
        # we provided, which will iterate over all N trigrams in the training
        # corpus.
        #
        # For each successive training example i, compute the stochastic
        # objective F_i(θ).  This is called the "forward" computation. Don't
        # forget to include the regularization term.
        #
        # To get the gradient of this objective (∇F_i(θ)), call the `backward`
        # method on the number you computed at the previous step.  This invokes
        # back-propagation to get the gradient of this number with respect to
        # the parameters θ.  This should be easier than implementing the
        # gradient method from the handout.
        #
        # Finally, update the parameters in the direction of the gradient, as
        # shown in Algorithm 1 in the reading handout.  You can do this `+=`
        # yourself, or you can call the `step` method of the `optimizer` object
        # we created above.  See the reading handout for more details on this.
        #
        # For the EmbeddingLogLinearLanguageModel, you should run SGD
        # optimization for 10 epochs and then stop.  You might want to print
        # progress dots using the `show_progress` method defined above.  Even
        # better, you could show a graphical progress bar using the tqdm module --
        # simply iterate over
        # instead of iterating over
        #     read_trigrams(file)
        #####################
        
        #torch.autograd.set_detect_anomaly(True)
        #with trange(10) as pbar:
            #for i in pbar:
        for i in range(10):
            total_loss = 0
            loss = 0
            
            for trigram in tqdm.tqdm(read_trigrams(file, self.vocab), total=N):
            #  for trigram in read_trigrams(file, self.vocab):
                loss = torch.log(self.prob(trigram[0],trigram[1],trigram[2]))      
                #loss += self.prob(trigram[0],trigram[1],trigram[2])
                
            
                l2_reg = torch.tensor(0.)
                for param in self.parameters():
                    l2_reg += torch.norm(param)

                loss = (loss - self.l2 * l2_reg)/N
                (-loss).backward()
                optimizer.step()
                optimizer.zero_grad() 
                #pdb.set_trace()
                total_loss = total_loss + loss.item()

        
            
            
            # if math.isnan(self.X[0][0].item()) :
            #      pdb.set_trace()
            #pdb.set_trace()
            #pbar.set_description(f"Epoch {i}: F = {loss.item()} ")
            print(f"epoch {i+1}: F = {total_loss} ")
       
        log.info("done optimizing.")

        # So how does the `backward` method work?
        #
        # As Python sees it, your parameters and the values that you compute
        # from them are not actually numbers.  They are `torch.Tensor` objects.
        # A Tensor may represent a numeric scalar, vector, matrix, etc.
        #
        # Every Tensor knows how it was computed.  For example, if you write `a
        # = b + exp(c)`, PyTorch not only computes `a` but also stores
        # backpointers in `a` that remember how the numeric value of `a` depends
        # on the numeric values of `b` and `c`.  In turn, `b` and `c` have their
        # own backpointers that remember what they depend on, and so on, all the
        # way back to the parameters.  This is just like the backpointers in
        # parsing!
        #
        # Every Tensor has a `backward` method that computes the gradient of its
        # numeric value with respect to the parameters, using "back-propagation"
        # through this computation graph.  In particular, once you've computed
        # the forward quantity F_i(θ) as a tensor, you can trace backwards to
        # get its gradient -- i.e., to find out how rapidly it would change if
        # each parameter were changed slightly.


        

        # So how does the `backward` method work?
        #
        # As Python sees it, your parameters and the values that you compute
        # from them are not actually numbers.  They are `torch.Tensor` objects.
        # A Tensor may represent a numeric scalar, vector, matrix, etc.
        #
        # Every Tensor knows how it was computed.  For example, if you write `a
        # = b + exp(c)`, PyTorch not only computes `a` but also stores
        # backpointers in `a` that remember how the numeric value of `a` depends
        # on the numeric values of `b` and `c`.  In turn, `b` and `c` have their
        # own backpointers that remember what they depend on, and so on, all the
        # way back to the parameters.  This is just like the backpointers in
        # parsing!
        #
        # Every Tensor has a `backward` method that computes the gradient of its
        # numeric value with respect to the parameters, using "back-propagation"
        # through this computation graph.  In particular, once you've computed
        # the forward quantity F_i(θ) as a tensor, you can trace backwards to
        # get its gradient -- i.e., to find out how rapidly it would change if
        # each parameter were changed slightly.


class ImprovedLogLinearLanguageModel(EmbeddingLogLinearLanguageModel):
    # TODO: IMPLEMENT ME!
    
    # This is where you get to come up with some features of your own, as
    # described in the reading handout.  This class inherits from
    # EmbeddingLogLinearLanguageModel and you can override anything, such as
    # `log_prob`.

    # OTHER OPTIONAL IMPROVEMENTS: You could override the `train` method.
    # Instead of using 10 epochs, try "improving the SGD training loop" as
    # described in the reading handout.  Some possibilities:
    #
    # * You can use the `draw_trigrams_forever` function that we
    #   provided to shuffle the trigrams on each epoch.
    #
    # * You can choose to compute F_i using a mini-batch of trigrams
    #   instead of a single trigram, and try to vectorize the computation
    #   over the mini-batch.
    #
    # * Instead of running for exactly 10*N trigrams, you can implement
    #   early stopping by giving the `train` method access to dev data.
    #   This will run for as long as continued training is helpful,
    #   so it might run for more or fewer than 10*N trigrams.
    #
    # * You could use a different optimization algorithm instead of SGD, such
    #   as `torch.optim.Adam` (https://pytorch.org/docs/stable/optim.html).
    #
    def prob(self, x: Wordtype, y: Wordtype, z: Wordtype) -> float:
        # This returns an ordinary float probability, using the
        # .item() method that extracts a number out of a Tensor.
        #pdb.set_trace()
            batchz = torch.zeros((len(z),self.dim),dtype=torch.float32)
            batchy = torch.zeros((len(z),self.dim),dtype=torch.float32)
            batchx = torch.zeros((len(z),self.dim),dtype=torch.float32)
            count = 0
            for zi in z:
                if (zi =="OOV" or zi not in self.lexicon.word_to_int.keys()):
                    zi = self.lexicon.embeddings[self.lexicon.word_to_int["OOL"]]
                else:
                    zi = self.lexicon.embeddings[self.lexicon.word_to_int[zi]] 
                batchz[count,:] = zi
                count+=1

            count = 0
            for yi in y:
                if (yi=="OOV" or yi not in self.lexicon.word_to_int.keys()):
                    yi = self.lexicon.embeddings[self.lexicon.word_to_int["OOL"]]
                else:
                    yi = self.lexicon.embeddings[self.lexicon.word_to_int[yi]] 
                batchy[count,:] = yi
                count+=1
            count = 0
            for xi in x:
                if (xi=="OOV" or xi not in self.lexicon.word_to_int.keys()):
                    xi = self.lexicon.embeddings[self.lexicon.word_to_int["OOL"]]
                else:
                    xi = self.lexicon.embeddings[self.lexicon.word_to_int[xi]] 
                batchx[count,:] = xi
                count+=1
            p = self.log_prob(batchx, batchy, batchz)
        # assert isinstance(p, float)  # checks that we'll adhere to the return type annotation, which is inherited from superclass
            return torch.exp(p)

    def log_prob(self, x: Wordtype, y: Wordtype, z: Wordtype) -> torch.Tensor:
        """Return log p(z | xy) according to this language model."""
        # TODO: IMPLEMENT ME!
        # Don't forget that you can create additional methods
        # that you think are useful, if you'd like.
        # It's cleaner than making this function massive.
        #
        # Be sure to use vectorization over the vocabulary to
        # compute the normalization constant Z, or this method
        # will be very slow.
        #
        # The operator `@` is a nice way to write matrix multiplication:
        # you can write J @ K as shorthand for torch.mul(J, K).
        # J @ K looks more like the usual math notation.
        #pdb.set_trace()
        x = x.double()
        y = y.double()
        z = x.double()
        Xmat = torch.matmul(x,self.X.double())
        Ymat =  torch.matmul(y,self.Y.double())
        # Z_den = torch.sum(torch.exp(torch.matmul(Xmat,torch.transpose(self.vocab_emb,0,1).double())
        #                      + torch.matmul(Ymat,torch.transpose(self.vocab_emb,0,1).double())))
        #if self.Z_den == None:
        Z_den = torch.logsumexp(torch.matmul(Xmat,torch.transpose(self.vocab_emb,0,1).double())
                                + torch.matmul(Ymat,torch.transpose(self.vocab_emb,0,1).double()),1)
        #else:
        #    Z_den = self.Z_den
        p_num = torch.logsumexp(torch.matmul(Xmat,torch.transpose(z,0,1)) + torch.matmul(Ymat,torch.transpose(z,0,1)),1)
        p = torch.sum(torch.log(p_num) - Z_den)
        #self.Z_den = Z_den.item()
        
        return p

    def train(self, file: Path):    # type: ignore
        
        ### Technically this method shouldn't be called `train`,
        ### because this means it overrides not only `LanguageModel.train` (as desired)
        ### but also `nn.Module.train` (which has a different type). 
        ### However, we won't be trying to use the latter method.
        ### The `type: ignore` comment above tells the type checker to ignore this inconsistency.
        
        # Optimization hyperparameters.
        gamma0 = 0.1  # initial learning rate

        # This is why we needed the nn.Parameter above.
        # The optimizer needs to know the list of parameters
        # it should be trying to update.
        optimizer = optim.SGD(self.parameters(), lr=gamma0)

        # Initialize the parameter matrices to be full of zeros.
        nn.init.zeros_(self.X)   # type: ignore
        nn.init.zeros_(self.Y)   # type: ignore

        N = num_tokens(file)
        log.info("Start optimizing on {N} training tokens...")

        #####################
        # TODO: Implement your SGD here by taking gradient steps on a sequence
        # of training examples.  Here's how to use PyTorch to make it easy:
        #
        # To get the training examples, you can use the `read_trigrams` function
        # we provided, which will iterate over all N trigrams in the training
        # corpus.
        #
        # For each successive training example i, compute the stochastic
        # objective F_i(θ).  This is called the "forward" computation. Don't
        # forget to include the regularization term.
        #
        # To get the gradient of this objective (∇F_i(θ)), call the `backward`
        # method on the number you computed at the previous step.  This invokes
        # back-propagation to get the gradient of this number with respect to
        # the parameters θ.  This should be easier than implementing the
        # gradient method from the handout.
        #
        # Finally, update the parameters in the direction of the gradient, as
        # shown in Algorithm 1 in the reading handout.  You can do this `+=`
        # yourself, or you can call the `step` method of the `optimizer` object
        # we created above.  See the reading handout for more details on this.
        #
        # For the EmbeddingLogLinearLanguageModel, you should run SGD
        # optimization for 10 epochs and then stop.  You might want to print
        # progress dots using the `show_progress` method defined above.  Even
        # better, you could show a graphical progress bar using the tqdm module --
        # simply iterate over
        # instead of iterating over
        #     read_trigrams(file)
        #####################
        
        #torch.autograd.set_detect_anomaly(True)
        #with trange(10) as pbar:
            #for i in pbar:
        batch_size=64
        batchx = []
        batchy = []
        batchz = []
        for i in range(10):
            total_loss = 0
            loss = 0
            
            for trigram in tqdm.tqdm(read_trigrams(file, self.vocab), total=N):
            #  for trigram in read_trigrams(file, self.vocab):
                count=0
                while count < batch_size:
                    batchx.append(trigram[0])
                    batchy.append(trigram[1])
                    batchz.append(trigram[2])
                    count+=1
                    #pdb.set_trace()
                loss = torch.log(self.prob(batchx,batchy,batchz))
                
                l2_reg = torch.tensor(0.)
                for param in self.parameters():
                    l2_reg += torch.norm(param)
                loss =  (loss - self.l2 * l2_reg)/N
                total_loss = total_loss + loss.item()
        
            
            (-loss).backward(retain_graph=True)
            optimizer.step()
            optimizer.zero_grad() 
            # if math.isnan(self.X[0][0].item()) :
            #      pdb.set_trace()
            #pdb.set_trace()
            #pbar.set_description(f"Epoch {i}: F = {loss.item()} ")
            print(f"epoch {i+1}: F = {total_loss} ")
       
        log.info("done optimizing.")
