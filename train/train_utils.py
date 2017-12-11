import os, sys, torch, pdb, datetime
from operator import itemgetter
import torch.autograd as autograd
import torch.nn.functional as F
import torch.utils.data as data
import torch.nn as nn
from tqdm import tqdm
import numpy as np
from sklearn import metrics
import meter
import itertools
import math


def runEncoderOnQuestions(samples, encoder_model, args):

    bodies, bodies_masks = autograd.Variable(samples['bodies']), autograd.Variable(samples['bodies_masks'])
    if args.cuda:
        bodies, bodies_masks = bodies.cuda(), bodies_masks.cuda()

    out_bodies = encoder_model(bodies, bodies_masks)

    titles, titles_masks = autograd.Variable(samples['titles']), autograd.Variable(samples['titles_masks'])
    if args.cuda:
        titles, titles_masks = titles.cuda(), titles_masks.cuda()

    out_titles = encoder_model(titles, titles_masks)

    hidden_rep = (out_bodies + out_titles)/2
    return hidden_rep


def train_model(train_data, dev_data, encoder_model, domain_discriminator, args):
    if args.cuda:
        encoder_model, domain_discriminator = encoder_model.cuda(), domain_discriminator.cuda()

    parameters = itertools.ifilter(lambda p: p.requires_grad, encoder_model.parameters())
    encoder_optimizer = torch.optim.Adam(parameters , lr=args.lr[0], weight_decay=args.weight_decay[0])

    domain_optimizer = torch.optim.Adam(domain_discriminator.parameters() , lr=args.lr[1], weight_decay=args.weight_decay[1])

    for epoch in range(1, args.epochs+1):
        print("-------------\nEpoch {}:\n".format(epoch))

        run_epoch(train_data, True, (encoder_model, encoder_optimizer), (domain_discriminator, domain_optimizer), args)

        model_path = args.save_path[:args.save_path.rfind(".")] + "_" + str(epoch) + args.save_path[args.save_path.rfind("."):]
        torch.save(encoder_model, model_path)

        print "*******dev********"
        run_epoch(dev_data, False, (encoder_model, encoder_optimizer), (domain_discriminator, domain_optimizer), args)



def test_model(test_data, encoder_model, args):
    if args.cuda:
        encoder_model = encoder_model.cuda()

    print "*******test********"
    run_epoch(test_data, False, (encoder_model, None) , (None, None), args)



def run_epoch(data, is_training, encoder_model_optimizer, domain_model_optimizer, args):
    '''
    Train model for one pass of train data, and return loss, acccuracy
    '''
    encoder_model, encoder_optimizer = encoder_model_optimizer
    domain_model, domain_optimizer = domain_model_optimizer

    data_loader = torch.utils.data.DataLoader(
        data,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        drop_last=True)

    losses = []

    if is_training:
        encoder_model.train()
        domain_model.train()
    else:
        encoder_model.eval()

    nll_loss = nn.NLLLoss()

    #y_true = []
    #y_scores = []

    auc_met = meter.AUCMeter()

    for batch in tqdm(data_loader):

        cosine_similarity = nn.CosineSimilarity(dim=0, eps=1e-6)
        criterion = nn.MultiMarginLoss(margin=0.4)
        #pdb.set_trace()

        if is_training:
            encoder_optimizer.zero_grad()
            domain_optimizer.zero_grad()

        ###source question encoder####
        if is_training:
            samples = batch['samples']
        else:
            samples = batch

        #output - batch of samples, where every sample is 2d tensor of avg hidden states
        hidden_rep = runEncoderOnQuestions(samples, encoder_model, args)

        #Calculate cosine similarities here and construct X_scores
        #expected datastructure of hidden_rep = batchsize x number_of_q x hidden_size
        cs_tensor = autograd.Variable(torch.FloatTensor(hidden_rep.size(0), hidden_rep.size(1)-1))

        if args.cuda:
            cs_tensor = cs_tensor.cuda()

        #calculate cosine similarity for every query vs. neg q pair
        for j in range(1, hidden_rep.size(1)):
            for i in range(hidden_rep.size(0)):
                cs_tensor[i, j-1] = cosine_similarity(hidden_rep[i, 0, ], hidden_rep[i, j, ])

        X_scores = torch.stack(cs_tensor, 0)
        y_targets = autograd.Variable(torch.zeros(hidden_rep.size(0)).type(torch.LongTensor))

        if args.cuda:
            y_targets = y_targets.cuda()

        if is_training:
            #####domain classifier#####
            cross_d_questions = batch['question']
            avg_hidden_rep = runEncoderOnQuestions(cross_d_questions, encoder_model, args)

            predicted_domains = domain_model(avg_hidden_rep)

            true_domains = autograd.Variable(cross_d_questions['domain']).squeeze(1)

            if args.cuda:
                true_domains = true_domains.cuda()

            domain_classifier_loss = nll_loss(predicted_domains, true_domains)
            print "Domain loss in batch", domain_classifier_loss.data

            #calculate loss
            encoder_loss = criterion(X_scores, y_targets)
            print "Encoder loss in batch", encoder_loss.data

            '''
            if encoder_loss.cpu().data.numpy().item() == 0:
                new_lambda = -new_lambda
            else:
                new_lambda = args.lambda_d * 10**(int(math.log10(encoder_loss.cpu().data.numpy().item())) - int(math.log10(domain_classifier_loss.cpu().data.numpy().item())))
            print "new lambda is ", new_lambda
            '''

            task_loss = encoder_loss - args.lambda_d * domain_classifier_loss
            print "Task loss in batch", task_loss.data
            print "\n\n"

            task_loss.backward()
            encoder_optimizer.step()
            domain_optimizer.step()

            losses.append(task_loss.cpu().data[0])

        else:

            for i in range(args.batch_size):

                for j in range(20):
                    y_true = 0
                    if j == 0:
                        y_true = 1

                    x = cs_tensor[i, j].data

                    if args.cuda:
                        x = x.cpu().numpy()
                    else:
                        x = x.numpy()

                    auc_met.add(x, y_true)


    # Calculate epoch level scores
    if is_training:
        avg_loss = np.mean(losses)
        print('Average Train loss: {:.6f}'.format(avg_loss))
        print()
    else:
        print "AUC:", auc_met.value(0.05)
