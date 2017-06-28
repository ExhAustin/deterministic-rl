import numpy as np
import math
import random
import tensorflow as tf
from keras import backend as K

from ActorCriticNet import ActorNetwork, CriticNetwork
from ReplayBuffer import ReplayBuffer

class DDPGLearner:
	def __init__(self, state_dim, action_dim,
		BATCH_SIZE=50,
		TAU=0.1,	#target network hyperparameter
		LRA=0.0001,	#learning rate for actor
		LRC=0.001,	#learning rate for critic
		GAMMA=0.99,
		HIDDEN1=300,
		HIDDEN2=600,
		verbose=True
		):

		self.BATCH_SIZE=BATCH_SIZE
		self.GAMMA = GAMMA
		self.verbose = verbose

		# Parameters and variables
		np.random.seed(1337)
		self.BUFFER_SIZE = 5000
		self.EXPLORE = 1000

		# Ornstein-Uhlenbeck Process
		self.mu_OU = 0
		self.theta_OU = 0.1
		self.sigma_OU = 0.2

		# Initialize variables
		self.epsilon = 1
		self.steps = 0

		# Tensorflow GPU optimization
		config = tf.ConfigProto()
		config.gpu_options.allow_growth = True
		sess = tf.Session(config=config)
		K.set_session(sess)

		# Initialize actor and critic
		if self.verbose: print('Creating actor network...')
		self.actor = ActorNetwork(sess, state_dim, action_dim, BATCH_SIZE, TAU, LRA, HIDDEN1, HIDDEN2)
		if self.verbose: print('Creating critic network...')
		self.critic = CriticNetwork(sess, state_dim, action_dim, BATCH_SIZE, TAU, LRC, HIDDEN1, HIDDEN2)
		self.buff = ReplayBuffer(self.BUFFER_SIZE)

	# Choose action
	def act(self, state_in, toggle_explore=True):
		# reshape 1d array input into keras format
		state = np.reshape(state_in, [1,-1])

		# Diminishing exploration
		if self.epsilon > 0:
			self.epsilon -= 1/self.EXPLORE
		else:
			self.epsilon = 0

		# Ornstein-Uhlenbeck Process
		OU = lambda x : self.theta_OU*(self.mu_OU - x) + self.sigma_OU*np.random.randn(1)

		# Produce action
		action_original = self.actor.model.predict(state)
		action_noise = toggle_explore*self.epsilon*OU(action_original)
		
		# Record step
		self.steps += 1

		# Clip, reshape and output
		action_out =  np.clip(action_original + action_noise, -1, 1)
		return action_out[0,:]

	# Recieve reward and learn
	def learn(self, state_in, action_in, reward, new_state_in, done):
		# reshape 1d array inputs into keras format
		state = np.reshape(state_in, [1,-1])
		action = np.reshape(action_in, [1,-1])
		new_state = np.reshape(new_state_in, [1,-1])

		# Save experience in buffer
		self.buff.add(state, action, reward, new_state, done)

		# Extract batch
		batch, batchsize = self.buff.getBatch(self.BATCH_SIZE)
		states = np.concatenate([e[0] for e in batch], axis=0)
		actions = np.concatenate([e[1] for e in batch], axis=0)
		rewards = np.asarray([e[2] for e in batch])
		new_states = np.concatenate([e[3] for e in batch], axis=0)
		dones = np.asarray([e[4] for e in batch])

		# Train critic
		target_q_values = self.critic.target_model.predict([new_states, self.actor.target_model.predict(new_states)])	
		y = np.empty([batchsize])
		loss = 0
		for k in range(len(batch)):
			if dones[k]:
				y[k] = rewards[k]
			else:
				y[k] = rewards[k] + self.GAMMA*target_q_values[k]	

		loss = self.critic.model.train_on_batch([states, actions], y)

		# Train actor
		a_for_grad = self.actor.model.predict(states)
		grads = self.critic.gradients(states, a_for_grad)
		self.actor.train(states, grads)

		# Update target networks
		self.actor.target_train()
		self.critic.target_train()

		# Print training info
		if self.verbose:
			print('steps={}, loss={}'.format(self.steps, loss))

		# Return loss
		return loss