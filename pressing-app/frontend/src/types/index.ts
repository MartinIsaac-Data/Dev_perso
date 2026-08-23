export type Role = "SUPER_ADMIN" | "ADMIN" | "MANAGER" | "CASHIER" | "OPERATOR" | "DELIVERY";

export interface AuthUser {
  id: string;
  email: string;
  fullName: string;
  role: Role;
  branchId: string | null;
  branchIds: string[];
  permissions: string[];
}

export interface Branch {
  id: string;
  name: string;
  address?: string | null;
  phone?: string | null;
  managerId?: string | null;
}

export type CustomerType = "INDIVIDUAL" | "COMPANY" | "VIP";

export interface Customer {
  id: string;
  fullName: string;
  phone: string;
  email?: string | null;
  address?: string | null;
  type: CustomerType;
  notes?: string | null;
  active: boolean;
  createdAt: string;
  _count?: { orders: number };
}

export interface Service {
  id: string;
  name: string;
  description?: string | null;
  category: string;
  price: string | number;
  expressPrice?: string | number | null;
  standardDurationHours: number;
  expressDurationHours?: number | null;
  active: boolean;
}

export type OrderStatus =
  | "RECEIVED"
  | "INSPECTION"
  | "PROCESSING"
  | "QUALITY_CHECK"
  | "READY"
  | "OUT_FOR_DELIVERY"
  | "DELIVERED"
  | "COMPLETED"
  | "CANCELLED";

export type PaymentStatus = "UNPAID" | "PARTIAL" | "PAID" | "REFUNDED";
export type PaymentMethod = "CASH" | "ORANGE_MONEY" | "MTN_MOMO" | "CARD" | "BANK_TRANSFER" | "OTHER";
export type DeliveryStatusValue = "PENDING" | "ASSIGNED" | "PICKED_UP" | "IN_TRANSIT" | "DELIVERED" | "FAILED";

export interface Delivery {
  id: string;
  orderId: string;
  order?: Order;
  type: "PICKUP" | "DELIVERY";
  address?: string | null;
  neighborhood?: string | null;
  city?: string | null;
  phone?: string | null;
  delivererId?: string | null;
  deliverer?: { id: string; fullName: string; phone?: string | null } | null;
  fee: string | number;
  scheduledDate?: string | null;
  deliveredDate?: string | null;
  status: DeliveryStatusValue;
}

export interface OrderItem {
  id: string;
  category: string;
  articleType: string;
  quantity: number;
  color?: string | null;
  brand?: string | null;
  size?: string | null;
  serviceId: string;
  service?: Service;
  isExpress: boolean;
  unitPrice: string | number;
  totalPrice: string | number;
}

export interface Payment {
  id: string;
  amount: string | number;
  method: PaymentMethod;
  paidAt: string;
  reference?: string | null;
}

export interface OrderStatusHistoryEntry {
  id: string;
  status: OrderStatus;
  note?: string | null;
  createdAt: string;
}

export interface Order {
  id: string;
  orderNumber: string;
  customerId: string;
  customer?: Customer;
  status: OrderStatus;
  priority: "NORMAL" | "EXPRESS";
  depositDate: string;
  estimatedReadyDate?: string | null;
  completedDate?: string | null;
  subtotal: string | number;
  discount: string | number;
  deliveryFee: string | number;
  total: string | number;
  paidAmount: string | number;
  balance: string | number;
  paymentStatus: PaymentStatus;
  notes?: string | null;
  items: OrderItem[];
  payments?: Payment[];
  statusHistory?: OrderStatusHistoryEntry[];
  employee?: { id: string; fullName: string } | null;
}

export interface Paginated<T> {
  data: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface DashboardData {
  range: { from: string; to: string };
  kpis: {
    revenueToday: number;
    revenueMonth: number;
    ordersToday: number;
    ordersInProgress: number;
    ordersReady: number;
    ordersLate: number;
    ordersDelivered: number;
    customerCount: number;
    paymentsPending: number;
    expensesToday: number;
    estimatedProfit: number;
  };
  charts: {
    dailyRevenue: { date: string; total: number }[];
    ordersByStatus: { status: string; count: number }[];
    topServices: { name: string; count: number; revenue: number }[];
    topArticles: { category: string; quantity: number }[];
    employeePerformance: { name: string; orders: number; revenue: number }[];
    paymentMethodBreakdown: { method: string; total: number }[];
  };
}
