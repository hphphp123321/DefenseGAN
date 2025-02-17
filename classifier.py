# borrowed from https://github.com/pytorch/examples/blob/master/mnist/main.py
import torch
import argparse
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import DataLoader

from attacks import FGSM
from utils import get_mnist_ds, mkdir
from modules import CNNClassifier, MLPClassifier


def update(model, optimizer, x, y):
    optimizer.zero_grad()
    output = model(x)
    loss = F.cross_entropy(output, y)
    loss.backward()
    optimizer.step()
    return loss


def train(args, model, device, train_loader, optimizer, epoch):
    model.train()
    for batch_idx, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)
        loss = update(model, optimizer, data, target)
        if args.adv:
            model.train()
            adv_data = FGSM(model, 0.3)._attack(data, target)
            model.train()
            update(model, optimizer, adv_data, target)
        if batch_idx % args.log_interval == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(epoch, batch_idx * len(data),
                                                                           len(train_loader.dataset),
                                                                           100. * batch_idx / len(train_loader),
                                                                           loss.item()))


def test(args, model, device, test_loader):
    model.eval()
    test_loss = 0
    correct = 0
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += F.cross_entropy(output, target, reduction='sum').item()  # sum up batch loss
            pred = output.argmax(dim=1, keepdim=True)  # get the index of the max log-probability
            correct += pred.eq(target.view_as(pred)).sum().item()
    test_loss /= len(test_loader.dataset)
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.2f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        100. * correct / len(test_loader.dataset)))
    return correct


def main():
    parser = argparse.ArgumentParser(description='PyTorch MNIST Example')
    parser.add_argument('--batch-size', type=int, default=64, metavar='N',
                        help='input batch size for training (default: 64)')
    parser.add_argument('--test-batch-size', type=int, default=1000, metavar='N',
                        help='input batch size for testing (default: 1000)')
    parser.add_argument('--epochs', type=int, default=10, metavar='N',
                        help='number of epochs to train (default: 10)')
    parser.add_argument('--lr', type=float, default=0.01, metavar='LR',
                        help='learning rate (default: 0.01)')
    parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                        help='SGD momentum (default: 0.5)')
    parser.add_argument('--no-cuda', action='store_true', default=False,
                        help='disables CUDA training')
    parser.add_argument('--seed', type=int, default=1, metavar='S',
                        help='random seed (default: 1)')
    parser.add_argument('--log-interval', type=int, default=1000, metavar='N',
                        help='how many batches to wait before logging training status')
    parser.add_argument('--mlp', action='store_true')
    parser.add_argument('--adv', action='store_true', help='adversarial training')
    args = parser.parse_args()
    use_cuda = not args.no_cuda and torch.cuda.is_available()
    torch.manual_seed(args.seed)
    device = torch.device("cuda" if use_cuda else "cpu")
    kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}
    train_loader = DataLoader(get_mnist_ds(32, True), batch_size=args.batch_size, shuffle=True, **kwargs)
    test_loader = DataLoader(get_mnist_ds(32, False), batch_size=args.test_batch_size, shuffle=False, **kwargs)
    model = (MLPClassifier() if args.mlp else CNNClassifier()).to(device)
    optimizer = optim.SGD(model.parameters(), lr=args.lr, momentum=args.momentum)
    best_num_correct = -1
    mkdir('./trained_models/')
    for epoch in range(1, args.epochs + 1):
        train(args, model, device, train_loader, optimizer, epoch)
        correct = test(args, model, device, test_loader)
        if correct > best_num_correct:
            best_num_correct = correct
            torch.save(model.state_dict(), './trained_models/mnist_{}{}.pt'
                       .format('mlp' if args.mlp else 'cnn', '_adv' if args.adv else ''))
    print('best:', best_num_correct)


if __name__ == '__main__':
    main()
